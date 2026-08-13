import logging
import time
from typing import Any

import redis

from app.bidding.client.dto import BidReviewCallbackRequest
from app.bidding.client.spring_bid_review_client import SpringBidReviewClient
from app.bidding.exceptions import (
    SpringBiddingAuthError,
    SpringBiddingBadRequestError,
    SpringBiddingJobNotFoundError,
    SpringBiddingTemporaryError,
)
from app.bidding.service.bid_review_processor import BidReviewProcessor
from app.bidding.worker.message import BidReviewJobMessage
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BidReviewRedisWorker:
    """입찰 문서 비교 검토 Redis 작업을 가져와 Spring callback까지 처리합니다."""

    def __init__(
        self,
        settings: Settings,
        redis_client: Any | None = None,
        spring_client: SpringBidReviewClient | None = None,
        processor: BidReviewProcessor | None = None,
    ):
        self._settings = settings
        self._redis = redis_client or redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self._spring_client = spring_client or SpringBidReviewClient(settings)
        self._processor = processor or BidReviewProcessor(settings)

    def run_forever(self) -> None:
        self._ensure_consumer_group()
        logger.info(
            "Bidding review worker started stream=%s group=%s consumer=%s",
            self._settings.bidding_review_stream_key,
            self._settings.bidding_review_consumer_group,
            self._settings.bidding_review_consumer_name,
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
            groupname=self._settings.bidding_review_consumer_group,
            consumername=self._settings.bidding_review_consumer_name,
            streams={self._settings.bidding_review_stream_key: ">"},
            count=1,
            block=block_ms,
        )
        for _, stream_messages in messages or []:
            for message_id, raw_payload in stream_messages:
                self._handle_message(message_id, raw_payload)

    def _claim_stale_messages(self) -> list[tuple[str, dict[str, Any]]]:
        """ACK되지 않은 오래된 작업을 현재 consumer로 회수합니다."""
        result = self._redis.xautoclaim(
            name=self._settings.bidding_review_stream_key,
            groupname=self._settings.bidding_review_consumer_group,
            consumername=self._settings.bidding_review_consumer_name,
            min_idle_time=self._settings.bidding_review_claim_min_idle_ms,
            start_id="0-0",
            count=self._settings.bidding_review_claim_count,
        )
        if not result or len(result) < 2:
            return []
        return result[1]

    def _handle_message(self, message_id: str, raw_payload: dict[str, Any]) -> None:
        try:
            message = BidReviewJobMessage.model_validate(raw_payload)
        except Exception:
            logger.exception("Invalid bidding review message messageId=%s", message_id)
            self._ack(message_id)
            return

        logger.info(
            "Bidding review job received reviewId=%s attemptId=%s retryCount=%s",
            message.review_id,
            message.attempt_id,
            message.retry_count,
        )

        try:
            job = self._spring_client.get_review_job(
                message.review_id,
                message.attempt_id,
            )
        except (SpringBiddingJobNotFoundError, SpringBiddingBadRequestError):
            logger.warning(
                "Bidding review job ignored reviewId=%s attemptId=%s",
                message.review_id,
                message.attempt_id,
            )
            self._ack(message_id)
            return
        except (SpringBiddingAuthError, SpringBiddingTemporaryError):
            logger.exception(
                "Bidding review job load temporarily failed reviewId=%s attemptId=%s",
                message.review_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except Exception:
            logger.exception(
                "Bidding review job response invalid reviewId=%s attemptId=%s",
                message.review_id,
                message.attempt_id,
            )
            if self._send_failed_callback(
                message.review_id,
                message.attempt_id,
                "입찰 문서 검토 작업 조회 응답이 올바르지 않습니다.",
            ):
                self._ack(message_id)
            return

        if job.company_id != message.company_id:
            logger.warning(
                "Bidding review job ignored reviewId=%s attemptId=%s reason=company_mismatch",
                message.review_id,
                message.attempt_id,
            )
            self._ack(message_id)
            return

        try:
            callback = self._processor.process(job)
            callback_response = self._spring_client.send_review_callback(
                job.review_id,
                callback,
            )
        except (SpringBiddingAuthError, SpringBiddingTemporaryError):
            logger.exception(
                "Bidding review callback temporarily failed reviewId=%s attemptId=%s",
                message.review_id,
                message.attempt_id,
            )
            time.sleep(5)
            return
        except Exception:
            logger.exception(
                "Bidding review processing failed reviewId=%s attemptId=%s",
                message.review_id,
                message.attempt_id,
            )
            if self._send_failed_callback(
                job.review_id,
                job.attempt_id,
                "입찰 문서 검토 처리 중 오류가 발생했습니다.",
            ):
                self._ack(message_id)
            return

        logger.info(
            "Bidding review callback completed reviewId=%s attemptId=%s accepted=%s status=%s",
            callback_response.review_id,
            job.attempt_id,
            callback_response.accepted,
            callback_response.review_status,
        )
        self._ack(message_id)

    def _send_failed_callback(
        self,
        review_id: int,
        attempt_id: str,
        error_message: str,
        retryable: bool = False,
    ) -> bool:
        callback = BidReviewCallbackRequest.failed(
            attempt_id,
            "PROCESSING_ERROR",
            error_message,
            retryable=retryable,
        )
        try:
            response = self._spring_client.send_review_callback(review_id, callback)
        except (SpringBiddingAuthError, SpringBiddingTemporaryError):
            logger.exception(
                "Bidding review failed callback temporarily rejected reviewId=%s attemptId=%s",
                review_id,
                attempt_id,
            )
            time.sleep(5)
            return False
        except Exception:
            logger.exception(
                "Bidding review failed callback rejected reviewId=%s attemptId=%s",
                review_id,
                attempt_id,
            )
            return False

        logger.warning(
            "Bidding review failed callback completed reviewId=%s attemptId=%s accepted=%s status=%s",
            response.review_id,
            attempt_id,
            response.accepted,
            response.review_status,
        )
        # accepted=false도 오래된 시도에 대한 정상 멱등 응답이므로 ACK합니다.
        return True

    def _ensure_consumer_group(self) -> None:
        try:
            self._redis.xgroup_create(
                name=self._settings.bidding_review_stream_key,
                groupname=self._settings.bidding_review_consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _ack(self, message_id: str) -> None:
        self._redis.xack(
            self._settings.bidding_review_stream_key,
            self._settings.bidding_review_consumer_group,
            message_id,
        )


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    BidReviewRedisWorker(settings).run_forever()


if __name__ == "__main__":
    main()
