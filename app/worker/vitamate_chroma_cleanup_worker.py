import json
import logging
import time
from typing import Any

import redis
from pydantic import ValidationError

from app.client.dto import VitamateChromaCleanupCallbackRequest
from app.client.spring_vitamate_client import SpringVitamateClient
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    SpringVitamateAuthError,
    SpringVitamateBadRequestError,
    SpringVitamateJobNotFoundError,
    SpringVitamateTemporaryError,
)
from app.service.chroma.vitamate_chroma_cleanup_service import (
    VitamateChromaCleanupService,
)
from app.worker.message import VitamateChromaCleanupJobMessage


logger = logging.getLogger(__name__)


class VitamateChromaCleanupRedisWorker:
    # Redis Stream의 ChromaDB 벡터 삭제 작업을 처리합니다.

    def __init__(
        self,
        settings: Settings,
        spring_client: SpringVitamateClient | None = None,
        cleanup_service: VitamateChromaCleanupService | None = None,
    ):
        self._settings = settings
        self._redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self._spring_client = spring_client or SpringVitamateClient(settings)
        self._cleanup_service = cleanup_service or VitamateChromaCleanupService(
            settings
        )
        # Redis Pending 메시지를 순차적으로 탐색할 XAUTOCLAIM cursor입니다.
        self._claim_cursor = "0-0"

    def run_forever(self) -> None:
        # consumer group을 준비하고 cleanup 메시지를 계속 처리합니다.
        self._ensure_consumer_group()

        logger.info(
            "Vitamate Chroma cleanup worker started "
            "stream=%s group=%s consumer=%s",
            self._settings.vitamate_chroma_cleanup_stream_key,
            self._settings.vitamate_chroma_cleanup_consumer_group,
            self._settings.vitamate_chroma_cleanup_consumer_name,
        )

        while True:
            self.consume_once(block_ms=5000)

    def consume_once(self, block_ms: int = 5000) -> None:
        # 오래 멈춘 Pending 메시지를 먼저 회수한 뒤 신규 메시지를 읽습니다.
        self._ensure_consumer_group()

        if self._recover_stale_messages():
            return

        messages = self._redis.xreadgroup(
            groupname=self._settings.vitamate_chroma_cleanup_consumer_group,
            consumername=self._settings.vitamate_chroma_cleanup_consumer_name,
            streams={
                self._settings.vitamate_chroma_cleanup_stream_key: ">",
            },
            count=1,
            block=block_ms,
        )

        if not messages:
            return

        for _, stream_messages in messages:
            for message_id, raw_payload in stream_messages:
                self._handle_message(message_id, raw_payload)
        

    def _handle_message(
        self,
        message_id: str,
        raw_payload: dict[str, Any],
    ) -> None:
        # 메시지를 검증한 뒤 PROCESSING부터 최종 callback까지 처리합니다.
        try:
            message = VitamateChromaCleanupJobMessage.model_validate(
                raw_payload
            )
        except (ValidationError, ValueError, json.JSONDecodeError):
            logger.warning(
                "Invalid Chroma cleanup message messageId=%s",
                message_id,
            )
            self._publish_invalid_message_to_dlq(message_id)
            self._ack(message_id)
            return

        logger.info(
            "Vitamate Chroma cleanup job received "
            "cleanupJobId=%s retryCount=%s fileVersionCount=%s",
            message.cleanup_job_id,
            message.retry_count,
            len(message.file_version_ids),
        )

        try:
            processing_response = self._send_callback(
                message=message,
                status="PROCESSING",
                retryable=False,
            )

            # 현재 실행 시도가 아니거나 이미 끝난 작업이면 중복 처리하지 않습니다.
            if not processing_response.accepted:
                logger.warning(
                    "Vitamate Chroma cleanup job ignored "
                    "cleanupJobId=%s reason=%s",
                    message.cleanup_job_id,
                    processing_response.reason,
                )
                self._ack(message_id)
                return

            deleted_count = self._cleanup_service.cleanup(
                message.file_version_ids
            )

            completed_response = self._send_callback(
                message=message,
                status="COMPLETED",
                retryable=False,
                deleted_vector_count=deleted_count,
            )

            if not completed_response.accepted:
                logger.warning(
                    "Vitamate Chroma cleanup completion ignored "
                    "cleanupJobId=%s reason=%s",
                    message.cleanup_job_id,
                    completed_response.reason,
                )

            logger.info(
                "Vitamate Chroma cleanup job completed "
                "cleanupJobId=%s deletedVectorCount=%s",
                message.cleanup_job_id,
                deleted_count,
            )
            self._ack(message_id)

        except SpringVitamateAuthError:
            # 토큰 설정 오류는 운영자가 설정을 수정해야 하므로 ACK하지 않습니다.
            logger.exception(
                "Vitamate Chroma cleanup authentication failed "
                "cleanupJobId=%s",
                message.cleanup_job_id,
            )
            time.sleep(5)

        except SpringVitamateTemporaryError:
            # Spring이 일시적으로 응답하지 않으면 메시지를 ACK하지 않습니다.
            logger.exception(
                "Temporary Spring callback failure cleanupJobId=%s",
                message.cleanup_job_id,
            )
            time.sleep(5)

        except SpringVitamateJobNotFoundError:
            # DB에 작업이 없으면 더 처리할 수 없으므로 메시지를 종료합니다.
            logger.warning(
                "Vitamate Chroma cleanup job not found cleanupJobId=%s",
                message.cleanup_job_id,
            )
            self._ack(message_id)

        except SpringVitamateBadRequestError:
            # Spring 계약에 맞지 않는 요청은 반복해도 성공하지 않습니다.
            logger.exception(
                "Spring rejected Chroma cleanup callback cleanupJobId=%s",
                message.cleanup_job_id,
            )
            self._publish_message_to_dlq(
                message=message,
                error_code="SPRING_BAD_REQUEST",
                error_message="Spring rejected cleanup callback",
            )
            self._ack(message_id)

        except ValueError as exc:
            # 잘못된 파일 버전 목록은 재시도하지 않고 DLQ로 보냅니다.
            self._handle_processing_failure(
                message_id=message_id,
                message=message,
                retryable=False,
                error_code="INVALID_CLEANUP_REQUEST",
                error_message=str(exc),
            )

        except Exception:
            # ChromaDB 연결 실패 등 예측하지 못한 장애는 재시도 대상으로 처리합니다.
            logger.exception(
                "Vitamate Chroma cleanup processing failed cleanupJobId=%s",
                message.cleanup_job_id,
            )
            self._handle_processing_failure(
                message_id=message_id,
                message=message,
                retryable=True,
                error_code="CHROMA_CLEANUP_FAILED",
                error_message="Chroma vector cleanup failed",
            )

    def _handle_processing_failure(
        self,
        message_id: str,
        message: VitamateChromaCleanupJobMessage,
        retryable: bool,
        error_code: str,
        error_message: str,
    ) -> None:
        # 실패 결과를 Spring에 전달하고 재시도 또는 DLQ 상태를 처리합니다.
        try:
            response = self._send_callback(
                message=message,
                status="FAILED",
                retryable=retryable,
                error_code=error_code,
                error_message=error_message,
            )
        except (SpringVitamateAuthError, SpringVitamateTemporaryError):
            logger.exception(
                "Vitamate Chroma cleanup failure callback unavailable "
                "cleanupJobId=%s",
                message.cleanup_job_id,
            )
            return

        if response.cleanup_status == "DEAD_LETTER":
            self._publish_message_to_dlq(
                message=message,
                error_code=error_code,
                error_message=error_message,
            )

        # RETRY_WAIT이면 Spring이 새 Outbox 메시지를 만들기 때문에 현재 메시지는 종료합니다.
        self._ack(message_id)

    def _send_callback(
        self,
        message: VitamateChromaCleanupJobMessage,
        status: str,
        retryable: bool,
        deleted_vector_count: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ):
        # 현재 attemptId와 cleanup 처리 결과를 Spring에 전달합니다.
        response = self._spring_client.send_chroma_cleanup_callback(
            cleanup_job_id=message.cleanup_job_id,
            callback=VitamateChromaCleanupCallbackRequest(
                attemptId=message.attempt_id,
                status=status,
                retryable=retryable,
                deletedVectorCount=deleted_vector_count,
                errorCode=error_code,
                errorMessage=error_message,
            ),
        )

        logger.info(
            "Vitamate Chroma cleanup callback completed "
            "cleanupJobId=%s accepted=%s status=%s",
            response.cleanup_job_id,
            response.accepted,
            response.cleanup_status,
        )
        return response

    def _publish_invalid_message_to_dlq(self, message_id: str) -> None:
        # 파싱할 수 없는 메시지는 원문 대신 식별자와 오류 코드만 DLQ에 저장합니다.
        self._redis.xadd(
            self._settings.vitamate_chroma_cleanup_dlq_stream_key,
            {
                "sourceMessageId": message_id,
                "errorCode": "INVALID_CLEANUP_MESSAGE",
                "errorMessage": "Cleanup message validation failed",
            },
        )

    def _publish_message_to_dlq(
        self,
        message: VitamateChromaCleanupJobMessage,
        error_code: str,
        error_message: str,
    ) -> None:
        # 재처리가 필요한 최소 정보만 DLQ에 저장합니다.
        self._redis.xadd(
            self._settings.vitamate_chroma_cleanup_dlq_stream_key,
            {
                "cleanupJobId": str(message.cleanup_job_id),
                "cleanupKey": message.cleanup_key,
                "attemptId": message.attempt_id,
                "fileVersionIds": json.dumps(message.file_version_ids),
                "retryCount": str(message.retry_count),
                "errorCode": error_code,
                "errorMessage": error_message[:500],
            },
        )

        logger.warning(
            "Vitamate Chroma cleanup job moved to DLQ cleanupJobId=%s",
            message.cleanup_job_id,
        )

    def _recover_stale_messages(self) -> bool:
        # 일정 시간 이상 ACK되지 않은 Pending 메시지를 현재 worker가 회수합니다.
        result = self._redis.xautoclaim(
            name=self._settings.vitamate_chroma_cleanup_stream_key,
            groupname=self._settings.vitamate_chroma_cleanup_consumer_group,
            consumername=self._settings.vitamate_chroma_cleanup_consumer_name,
            min_idle_time=(
                self._settings
                .vitamate_chroma_cleanup_claim_min_idle_ms
            ),
            start_id=self._claim_cursor,
            count=self._settings.vitamate_chroma_cleanup_claim_count,
        )

        if not result:
            self._claim_cursor = "0-0"
            return False

        self._claim_cursor = result[0]
        claimed_messages = result[1]

        if not claimed_messages:
            if self._claim_cursor == "0-0":
                self._claim_cursor = "0-0"
            return False

        logger.warning(
            "Vitamate Chroma cleanup Pending messages reclaimed count=%s",
            len(claimed_messages),
        )

        for message_id, raw_payload in claimed_messages:
            self._handle_message(message_id, raw_payload)

        return True
    
    def _ensure_consumer_group(self) -> None:
        # cleanup consumer group이 없으면 생성합니다.
        try:
            self._redis.xgroup_create(
                name=self._settings.vitamate_chroma_cleanup_stream_key,
                groupname=self._settings.vitamate_chroma_cleanup_consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _ack(self, message_id: str) -> None:
        # 처리가 끝난 Redis Stream 메시지를 ACK합니다.
        self._redis.xack(
            self._settings.vitamate_chroma_cleanup_stream_key,
            self._settings.vitamate_chroma_cleanup_consumer_group,
            message_id,
        )


def main() -> None:
    # CLI에서 Chroma cleanup worker를 실행합니다.
    logging.basicConfig(level=logging.INFO)
    worker = VitamateChromaCleanupRedisWorker(get_settings())
    worker.run_forever()


if __name__ == "__main__":
    main()