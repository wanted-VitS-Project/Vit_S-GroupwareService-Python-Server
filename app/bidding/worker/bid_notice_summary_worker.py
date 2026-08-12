import logging
import time
from typing import Any

import redis

from app.bidding.client.dto import BidNoticeSummaryCallbackRequest
from app.bidding.client.spring_bidding_client import SpringBiddingClient
from app.bidding.exceptions import (
    BiddingSummaryGenerateError,
    SpringBiddingAuthError,
    SpringBiddingBadRequestError,
    SpringBiddingJobNotFoundError,
    SpringBiddingTemporaryError,
)
from app.bidding.service.bid_notice_summary_processor import BidNoticeSummaryProcessor
from app.bidding.worker.message import BidNoticeSummaryJobMessage
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BidNoticeSummaryRedisWorker:
    """입찰 요약 Redis 작업을 가져와 Spring callback까지 처리합니다."""

    def __init__(
        self,
        settings: Settings,
        redis_client: Any | None = None,
        spring_client: SpringBiddingClient | None = None,
        processor: BidNoticeSummaryProcessor | None = None,
    ):
        self._settings = settings
        self._redis = redis_client or redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self._spring_client = spring_client or SpringBiddingClient(settings)
        self._processor = processor or BidNoticeSummaryProcessor(settings)

    def run_forever(self) -> None:
        self._ensure_consumer_group()
        logger.info(
            "Bidding summary worker started stream=%s group=%s consumer=%s",
            self._settings.bidding_summary_stream_key,
            self._settings.bidding_summary_consumer_group,
            self._settings.bidding_summary_consumer_name,
        )
        while True:
            self.consume_once(block_ms=5000)

    def consume_once(self, block_ms: int = 5000) -> None:
        self._ensure_consumer_group()
        claimed_messages = self._claim_stale_messages()
        if claimed_messages:
            for message_id, raw_payload in claimed_messages:
                self._handle_message(message_id, raw_payload)
            return

        messages = self._redis.xreadgroup(
            groupname=self._settings.bidding_summary_consumer_group,
            consumername=self._settings.bidding_summary_consumer_name,
            streams={self._settings.bidding_summary_stream_key: ">"},
            count=1,
            block=block_ms,
        )
        for _, stream_messages in messages or []:
            for message_id, raw_payload in stream_messages:
                self._handle_message(message_id, raw_payload)

    def _claim_stale_messages(self) -> list[tuple[str, dict[str, Any]]]:
        """ACK되지 않은 오래된 작업을 현재 consumer로 회수합니다."""
        result = self._redis.xautoclaim(
            name=self._settings.bidding_summary_stream_key,
            groupname=self._settings.bidding_summary_consumer_group,
            consumername=self._settings.bidding_summary_consumer_name,
            min_idle_time=self._settings.bidding_summary_claim_min_idle_ms,
            start_id="0-0",
            count=self._settings.bidding_summary_claim_count,
        )
        if not result or len(result) < 2:
            return []
        return result[1]

    def _handle_message(self, message_id: str, raw_payload: dict[str, Any]) -> None:
        try:
            message = BidNoticeSummaryJobMessage.model_validate(raw_payload)
        except Exception:
            logger.exception("Invalid bidding summary message messageId=%s", message_id)
            self._ack(message_id)
            return

        logger.info(
            "Bidding summary job received summaryId=%s attemptId=%s retryCount=%s",
            message.summary_id,
            message.attempt_id,
            message.retry_count,
        )

        try:
            job = self._spring_client.get_summary_job(
                message.summary_id,
                message.attempt_id,
            )
        except (SpringBiddingJobNotFoundError, SpringBiddingBadRequestError):
            logger.warning(
                "Bidding summary job ignored summaryId=%s attemptId=%s",
                message.summary_id,
                message.attempt_id,
            )
            self._ack(message_id)
            return
        except (SpringBiddingAuthError, SpringBiddingTemporaryError):
            logger.exception(
                "Bidding summary job load temporarily failed summaryId=%s attemptId=%s",
                message.summary_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except Exception:
            logger.exception(
                "Bidding summary job response invalid summaryId=%s attemptId=%s",
                message.summary_id,
                message.attempt_id,
            )
            if self._send_failed_callback(
                message.summary_id,
                message.attempt_id,
                "입찰 요약 작업 조회 응답이 올바르지 않습니다.",
            ):
                self._ack(message_id)
            return

        if job.company_id != message.company_id:
            logger.warning(
                "Bidding summary job ignored summaryId=%s attemptId=%s reason=company_mismatch",
                message.summary_id,
                message.attempt_id,
            )
            self._ack(message_id)
            return

        try:
            callback = self._processor.summarize(job)
            callback_response = self._spring_client.send_summary_callback(
                job.summary_id,
                callback,
            )
        except BiddingSummaryGenerateError as exc:
            logger.exception(
                "Bidding summary AI generation failed summaryId=%s attemptId=%s",
                message.summary_id,
                message.attempt_id,
            )
            if self._send_failed_callback(
                job.summary_id,
                job.attempt_id,
                "AI 입찰 요약 생성에 실패했습니다.",
                retryable=exc.retryable,
            ):
                self._ack(message_id)
            return
        except (SpringBiddingAuthError, SpringBiddingTemporaryError):
            logger.exception(
                "Bidding summary callback temporarily failed summaryId=%s attemptId=%s",
                message.summary_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except Exception:
            logger.exception(
                "Bidding summary processing failed summaryId=%s attemptId=%s",
                message.summary_id,
                message.attempt_id,
            )
            if self._send_failed_callback(
                job.summary_id,
                job.attempt_id,
                "입찰 요약 처리 중 오류가 발생했습니다.",
            ):
                self._ack(message_id)
            return

        logger.info(
            "Bidding summary callback completed summaryId=%s attemptId=%s accepted=%s status=%s",
            callback_response.summary_id,
            job.attempt_id,
            callback_response.accepted,
            callback_response.summary_status,
        )
        self._ack(message_id)

    def _send_failed_callback(
        self,
        summary_id: int,
        attempt_id: str,
        error_message: str,
        retryable: bool = False,
    ) -> bool:
        callback = BidNoticeSummaryCallbackRequest.failed(
            attempt_id,
            error_message,
            retryable=retryable,
        )
        try:
            response = self._spring_client.send_summary_callback(summary_id, callback)
        except (SpringBiddingAuthError, SpringBiddingTemporaryError):
            logger.exception(
                "Bidding summary failed callback temporarily rejected summaryId=%s attemptId=%s",
                summary_id,
                attempt_id,
            )
            time.sleep(5)
            return False
        except Exception:
            logger.exception(
                "Bidding summary failed callback rejected summaryId=%s attemptId=%s",
                summary_id,
                attempt_id,
            )
            return False

        logger.warning(
            "Bidding summary failed callback completed summaryId=%s attemptId=%s accepted=%s status=%s",
            response.summary_id,
            attempt_id,
            response.accepted,
            response.summary_status,
        )
        # accepted=false도 오래된 시도에 대한 정상 멱등 응답이므로 ACK합니다.
        return True

    def _ensure_consumer_group(self) -> None:
        try:
            self._redis.xgroup_create(
                name=self._settings.bidding_summary_stream_key,
                groupname=self._settings.bidding_summary_consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _ack(self, message_id: str) -> None:
        self._redis.xack(
            self._settings.bidding_summary_stream_key,
            self._settings.bidding_summary_consumer_group,
            message_id,
        )


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    BidNoticeSummaryRedisWorker(settings).run_forever()


if __name__ == "__main__":
    main()
