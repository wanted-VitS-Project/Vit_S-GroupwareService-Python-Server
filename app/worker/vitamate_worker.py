import logging
import time
from typing import Any

import redis

from app.service.vitamate_analysis_processor import VitamateAnalysisProcessor
from app.client.dto import VitamateCallbackRequest
from app.client.spring_vitamate_client import SpringVitamateClient
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    SpringVitamateAuthError,
    SpringVitamateBadRequestError,
    SpringVitamateJobNotFoundError,
    SpringVitamateTemporaryError,
    VitamateAiGenerateError,
)
from app.worker.message import VitamateAnalysisJobMessage

logger = logging.getLogger(__name__)


class VitamateRedisWorker:
    # Redis Stream 메시지를 읽고 Spring job 조회까지 연결하는 worker

    def __init__(self, settings: Settings):
        self._settings = settings
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self._spring_client = SpringVitamateClient(settings)
        self._processor = VitamateAnalysisProcessor(settings)

    def run_forever(self) -> None:
        # worker를 계속 실행하며 Redis Stream 메시지를 소비한다.
        self._ensure_consumer_group()

        logger.info(
            "Vitamate worker started stream=%s group=%s consumer=%s",
            self._settings.vitamate_stream_key,
            self._settings.vitamate_consumer_group,
            self._settings.vitamate_consumer_name,
        )

        while True:
            self.consume_once(block_ms=5000)

    def consume_once(self, block_ms: int = 5000) -> None:
        # 메시지를 한 번 읽고 처리한다. 테스트와 로컬 확인을 위해 한 번 실행 단위로 분리했다.
        self._ensure_consumer_group()

        messages = self._redis.xreadgroup(
            groupname=self._settings.vitamate_consumer_group,
            consumername=self._settings.vitamate_consumer_name,
            streams={self._settings.vitamate_stream_key: ">"},
            count=1,
            block=block_ms,
        )

        if not messages:
            return

        for _, stream_messages in messages:
            for message_id, raw_payload in stream_messages:
                self._handle_message(message_id, raw_payload)

    def _handle_message(self, message_id: str, raw_payload: dict[str, Any]) -> None:
        # Redis 메시지를 검증하고 Spring job 조회 API로 연결한다.
        try:
            message = VitamateAnalysisJobMessage.model_validate(raw_payload)
        except Exception:
            logger.exception("Invalid Vitamate job message messageId=%s", message_id)
            self._ack(message_id)
            return

        logger.info(
            "Vitamate job received analysisId=%s attemptId=%s retryCount=%s",
            message.analysis_id,
            message.attempt_id,
            message.retry_count,
        )

        try:
            job = self._spring_client.get_analysis_job(
                analysis_id=message.analysis_id,
                attempt_id=message.attempt_id,
            )
        except SpringVitamateJobNotFoundError:
            logger.warning(
                "Vitamate job ignored analysisId=%s attemptId=%s reason=not_found_or_stale",
                message.analysis_id,
                message.attempt_id,
            )
            self._ack(message_id)
            return
        except SpringVitamateBadRequestError:
            logger.exception(
                "Vitamate job rejected analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            self._ack(message_id)
            return
        except SpringVitamateAuthError:
            logger.exception(
                "Vitamate worker auth failed analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except SpringVitamateTemporaryError:
            logger.exception(
                "Temporary Spring failure analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except Exception:
            # 응답 형식이 계약과 안 맞는 경우(필드 누락 등) 포함 — worker 전체가 죽지 않도록 여기서 막는다.
            # 재시도해도 같은 응답이 다시 올 뿐이므로 FAILED 확정 후 ack한다(poison message 취급).
            logger.exception(
                "Vitamate job load response invalid analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            if self._send_failed_callback(
                message.analysis_id, message.attempt_id, "분석 작업 조회 응답이 올바르지 않습니다."
            ):
                self._ack(message_id)
            return

        logger.info(
            "Vitamate job loaded analysisId=%s attemptId=%s documentCount=%s",
            job.analysis_id,
            job.attempt_id,
            len(job.documents),
        )

        try:
            callback = self._processor.analyze(job)
            if callback.analysis_status == "FAILED":
                logger.warning(
                    "Vitamate analysis result marked failed analysisId=%s attemptId=%s reason=%s",
                    message.analysis_id,
                    message.attempt_id,
                    callback.error_message,
                )

            callback_response = self._spring_client.send_callback(
                analysis_id=job.analysis_id,
                callback=callback,
            )
        except VitamateAiGenerateError:
            logger.exception(
                "Vitamate AI generation failed analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            if self._send_failed_callback(job.analysis_id, job.attempt_id, "AI analysis failed"):
                self._ack(message_id)
            return
        except SpringVitamateAuthError:
            logger.exception(
                "Vitamate callback auth failed analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except SpringVitamateTemporaryError:
            logger.exception(
                "Temporary Spring callback failure analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except Exception:
            logger.exception(
                "Vitamate job processing failed analysisId=%s attemptId=%s",
                message.analysis_id,
                message.attempt_id,
            )
            if self._send_failed_callback(job.analysis_id, job.attempt_id, "AI analysis processing failed"):
                self._ack(message_id)
            return

        logger.info(
            "Vitamate callback completed analysisId=%s attemptId=%s accepted=%s status=%s",
            callback_response.analysis_id,
            job.attempt_id,
            callback_response.accepted,
            callback_response.analysis_status,
        )

        self._ack(message_id)

    def _send_failed_callback(
        self,
        analysis_id: int,
        attempt_id: str,
        error_message: str,
    ) -> bool:
        # 분석 실패 상태를 Spring에 저장해 PENDING/PROCESSING 상태가 멈추지 않게 합니다.
        # job 조회 자체가 실패한 경우에도 호출할 수 있도록 job 전체가 아니라 id만 받는다.
        callback = VitamateCallbackRequest(
            attemptId=attempt_id,
            analysisStatus="FAILED",
            result=None,
            citations=[],
            errorMessage=error_message,
        )

        try:
            callback_response = self._spring_client.send_callback(
                analysis_id=analysis_id,
                callback=callback,
            )
        except SpringVitamateAuthError:
            logger.exception(
                "Vitamate failed callback auth failed analysisId=%s attemptId=%s",
                analysis_id,
                attempt_id,
            )
            time.sleep(5)
            return False
        except SpringVitamateTemporaryError:
            logger.exception(
                "Temporary Spring failed callback failure analysisId=%s attemptId=%s",
                analysis_id,
                attempt_id,
            )
            time.sleep(5)
            return False
        except Exception:
            logger.exception(
                "Vitamate failed callback rejected analysisId=%s attemptId=%s",
                analysis_id,
                attempt_id,
            )
            return False

        logger.warning(
            "Vitamate failed callback completed analysisId=%s attemptId=%s accepted=%s status=%s",
            callback_response.analysis_id,
            attempt_id,
            callback_response.accepted,
            callback_response.analysis_status,
        )
        return callback_response.accepted

    def _ensure_consumer_group(self) -> None:
        # Redis Stream consumer group이 없으면 생성한다.
        try:
            self._redis.xgroup_create(
                name=self._settings.vitamate_stream_key,
                groupname=self._settings.vitamate_consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _ack(self, message_id: str) -> None:
        # 처리 완료된 메시지를 Redis Stream에서 ack 처리한다.
        self._redis.xack(
            self._settings.vitamate_stream_key,
            self._settings.vitamate_consumer_group,
            message_id,
        )


def main() -> None:
    # CLI에서 worker를 실행하기 위한 진입점
    logging.basicConfig(level=logging.INFO)
    worker = VitamateRedisWorker(get_settings())
    worker.run_forever()


if __name__ == "__main__":
    main()
