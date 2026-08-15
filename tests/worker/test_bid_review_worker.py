from unittest.mock import Mock, patch

from app.bidding.client.dto import (
    BidReviewCallbackRequest,
    BidReviewCallbackResponse,
    BidReviewJob,
)
from app.bidding.exceptions import (
    SpringBiddingJobNotFoundError,
    SpringBiddingTemporaryError,
)
from app.bidding.worker.bid_review_worker import BidReviewRedisWorker
from app.core.config import Settings


REVIEW_ID = 71
ATTEMPT_ID = "e0120882-8b6b-4cfc-9c3a-015cc3202ae6"
MESSAGE_ID = "message-1"


def test_consume_once_claims_stale_pending_message_before_new_messages():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    redis_client.xautoclaim.return_value = (
        "0-0",
        [(MESSAGE_ID, _raw_payload())],
        [],
    )
    spring_client.get_review_job.return_value = _job()
    processor.process.return_value = _completed_callback()
    spring_client.send_review_callback.return_value = _callback_response(True)

    worker.consume_once(block_ms=1)

    redis_client.xautoclaim.assert_called_once_with(
        name="bidding:review:jobs",
        groupname="bidding-review-workers",
        consumername="bidding-review-worker-local",
        min_idle_time=60_000,
        start_id="0-0",
        count=10,
    )
    redis_client.xreadgroup.assert_not_called()
    redis_client.xack.assert_called_once()


def test_consume_once_reads_new_message_when_no_stale_pending_message():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    redis_client.xautoclaim.return_value = ("0-0", [], [])
    redis_client.xreadgroup.return_value = [
        ("bidding:review:jobs", [(MESSAGE_ID, _raw_payload())])
    ]
    spring_client.get_review_job.return_value = _job()
    processor.process.return_value = _completed_callback()
    spring_client.send_review_callback.return_value = _callback_response(True)

    worker.consume_once(block_ms=1)

    redis_client.xreadgroup.assert_called_once_with(
        groupname="bidding-review-workers",
        consumername="bidding-review-worker-local",
        streams={"bidding:review:jobs": ">"},
        count=1,
        block=1,
    )
    redis_client.xack.assert_called_once()


def test_handle_message_sends_completed_callback_and_acks():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    callback = _completed_callback()
    spring_client.get_review_job.return_value = _job()
    processor.process.return_value = callback
    spring_client.send_review_callback.return_value = _callback_response(True)

    worker._handle_message(MESSAGE_ID, _raw_payload())

    spring_client.send_review_callback.assert_called_once_with(REVIEW_ID, callback)
    redis_client.xack.assert_called_once_with(
        "bidding:review:jobs",
        "bidding-review-workers",
        MESSAGE_ID,
    )


def test_handle_message_sends_failed_callback_produced_by_processor_and_acks():
    # processor가 다운로드·Gemini 실패를 이미 FAILED callback으로 감싸서 돌려준 경우 -
    # worker는 그대로 전송·ack만 하면 된다(별도 예외 분기 불필요).
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    failed_callback = BidReviewCallbackRequest.failed(
        ATTEMPT_ID, "AI_GENERATE_FAILED", "AI 문서 비교 검토 생성에 실패했습니다.", retryable=True
    )
    spring_client.get_review_job.return_value = _job()
    processor.process.return_value = failed_callback
    spring_client.send_review_callback.return_value = _callback_response(True, "PENDING")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_callback = spring_client.send_review_callback.call_args.args[1]
    assert sent_callback.review_status == "FAILED"
    assert sent_callback.retryable is True
    redis_client.xack.assert_called_once()


def test_handle_message_acks_stale_job_without_processing():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_review_job.side_effect = SpringBiddingJobNotFoundError("stale")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    processor.process.assert_not_called()
    redis_client.xack.assert_called_once()


def test_handle_message_acks_company_mismatch_without_processing():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    job = _job()
    job.company_id = 99
    spring_client.get_review_job.return_value = job

    worker._handle_message(MESSAGE_ID, _raw_payload())

    processor.process.assert_not_called()
    spring_client.send_review_callback.assert_not_called()
    redis_client.xack.assert_called_once()


@patch("app.bidding.worker.bid_review_worker.time.sleep")
def test_handle_message_does_not_ack_temporary_spring_failure(sleep):
    worker, redis_client, spring_client, _ = _worker_with_fakes()
    spring_client.get_review_job.side_effect = SpringBiddingTemporaryError("temporary")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    redis_client.xack.assert_not_called()
    sleep.assert_called_once_with(5)


def test_handle_message_reports_unexpected_processor_error_and_acks():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_review_job.return_value = _job()
    processor.process.side_effect = RuntimeError("unexpected bug")
    spring_client.send_review_callback.return_value = _callback_response(True, "FAILED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    callback = spring_client.send_review_callback.call_args.args[1]
    assert callback.review_status == "FAILED"
    assert callback.result is None
    assert callback.error_message == "입찰 문서 검토 처리 중 오류가 발생했습니다."
    redis_client.xack.assert_called_once()


def test_handle_message_acks_idempotent_callback_rejection():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_review_job.return_value = _job()
    processor.process.return_value = _completed_callback()
    spring_client.send_review_callback.return_value = _callback_response(False)

    worker._handle_message(MESSAGE_ID, _raw_payload())

    redis_client.xack.assert_called_once()


def test_handle_message_acks_invalid_message():
    worker, redis_client, _, _ = _worker_with_fakes()

    worker._handle_message(MESSAGE_ID, {"reviewId": "invalid"})

    redis_client.xack.assert_called_once()


def _worker_with_fakes():
    settings = Settings(_env_file=None, gemini_api_key="test-key")
    redis_client = Mock()
    spring_client = Mock()
    processor = Mock()
    worker = BidReviewRedisWorker(
        settings,
        redis_client=redis_client,
        spring_client=spring_client,
        processor=processor,
    )
    return worker, redis_client, spring_client, processor


def _raw_payload(attempt_id: str = ATTEMPT_ID, retry_count: int = 0) -> dict[str, object]:
    return {
        "reviewId": REVIEW_ID,
        "companyId": 10,
        "attemptId": attempt_id,
        "retryCount": retry_count,
    }


def _job(attempt_id: str = ATTEMPT_ID) -> BidReviewJob:
    return BidReviewJob(
        reviewId=REVIEW_ID,
        companyId=10,
        attemptId=attempt_id,
        prompt="보유 인력으로 수행 가능한지 검토해줘.",
        noticeId=1,
        noticeName="스마트시티 통합관제 용역",
    )


def _completed_callback(attempt_id: str = ATTEMPT_ID) -> BidReviewCallbackRequest:
    return BidReviewCallbackRequest.completed(attempt_id, "검토 결과입니다.", [], [])


def _callback_response(accepted: bool, status: str = "COMPLETED") -> BidReviewCallbackResponse:
    return BidReviewCallbackResponse(
        accepted=accepted,
        reviewId=REVIEW_ID,
        reviewStatus=status,
        reason=None if accepted else "attempt_mismatch_or_already_finished",
    )
