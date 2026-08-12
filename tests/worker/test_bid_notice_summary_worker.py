from unittest.mock import Mock, patch

from app.bidding.client.dto import (
    BidNoticeSummaryCallbackRequest,
    BidNoticeSummaryCallbackResponse,
    BidNoticeSummaryJob,
)
from app.bidding.exceptions import (
    BiddingSummaryGenerateError,
    SpringBiddingJobNotFoundError,
    SpringBiddingTemporaryError,
)
from app.bidding.worker.bid_notice_summary_worker import BidNoticeSummaryRedisWorker
from app.core.config import Settings


SUMMARY_ID = 1
ATTEMPT_ID = "e0120882-8b6b-4cfc-9c3a-015cc3202ae6"
MESSAGE_ID = "message-1"


def test_consume_once_claims_stale_pending_message_before_new_messages():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    redis_client.xautoclaim.return_value = (
        "0-0",
        [(MESSAGE_ID, _raw_payload())],
        [],
    )
    spring_client.get_summary_job.return_value = _job()
    processor.summarize.return_value = _completed_callback()
    spring_client.send_summary_callback.return_value = _callback_response(True)

    worker.consume_once(block_ms=1)

    redis_client.xautoclaim.assert_called_once_with(
        name="bidding:summary:jobs",
        groupname="bidding-summary-workers",
        consumername="bidding-summary-worker-local",
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
        ("bidding:summary:jobs", [(MESSAGE_ID, _raw_payload())])
    ]
    spring_client.get_summary_job.return_value = _job()
    processor.summarize.return_value = _completed_callback()
    spring_client.send_summary_callback.return_value = _callback_response(True)

    worker.consume_once(block_ms=1)

    redis_client.xreadgroup.assert_called_once_with(
        groupname="bidding-summary-workers",
        consumername="bidding-summary-worker-local",
        streams={"bidding:summary:jobs": ">"},
        count=1,
        block=1,
    )
    redis_client.xack.assert_called_once()


def test_handle_message_sends_completed_callback_and_acks():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    callback = _completed_callback()
    spring_client.get_summary_job.return_value = _job()
    processor.summarize.return_value = callback
    spring_client.send_summary_callback.return_value = _callback_response(True)

    worker._handle_message(MESSAGE_ID, _raw_payload())

    spring_client.send_summary_callback.assert_called_once_with(SUMMARY_ID, callback)
    redis_client.xack.assert_called_once_with(
        "bidding:summary:jobs",
        "bidding-summary-workers",
        MESSAGE_ID,
    )


def test_handle_message_acks_stale_job_without_processing():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_summary_job.side_effect = SpringBiddingJobNotFoundError("stale")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    processor.summarize.assert_not_called()
    redis_client.xack.assert_called_once()


def test_handle_message_acks_company_mismatch_without_processing():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    job = _job()
    job.company_id = 99
    spring_client.get_summary_job.return_value = job

    worker._handle_message(MESSAGE_ID, _raw_payload())

    processor.summarize.assert_not_called()
    spring_client.send_summary_callback.assert_not_called()
    redis_client.xack.assert_called_once()


@patch("app.bidding.worker.bid_notice_summary_worker.time.sleep")
def test_handle_message_does_not_ack_temporary_spring_failure(sleep):
    worker, redis_client, spring_client, _ = _worker_with_fakes()
    spring_client.get_summary_job.side_effect = SpringBiddingTemporaryError("temporary")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    redis_client.xack.assert_not_called()
    sleep.assert_called_once_with(5)


def test_handle_message_reports_ai_failure_and_acks():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_summary_job.return_value = _job()
    processor.summarize.side_effect = BiddingSummaryGenerateError("gemini failed")
    spring_client.send_summary_callback.return_value = _callback_response(True, "FAILED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    callback = spring_client.send_summary_callback.call_args.args[1]
    assert callback.summary_status == "FAILED"
    assert callback.overview_summary is None
    assert callback.error_message == "AI 입찰 요약 생성에 실패했습니다."
    assert callback.retryable is False
    redis_client.xack.assert_called_once()


def test_handle_message_reports_temporary_ai_failure_as_retryable_and_acks():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_summary_job.return_value = _job()
    processor.summarize.side_effect = BiddingSummaryGenerateError(
        "rate limited",
        retryable=True,
    )
    spring_client.send_summary_callback.return_value = _callback_response(
        True,
        "PENDING",
    )

    worker._handle_message(MESSAGE_ID, _raw_payload())

    callback = spring_client.send_summary_callback.call_args.args[1]
    assert callback.summary_status == "FAILED"
    assert callback.retryable is True
    redis_client.xack.assert_called_once()


def test_retry_message_completes_after_first_temporary_failure():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    second_attempt_id = "be54f33d-cfee-4a17-bf48-bce42dfcb388"
    first_job = _job()
    second_job = _job(second_attempt_id)
    completed_callback = _completed_callback(second_attempt_id)

    spring_client.get_summary_job.side_effect = [first_job, second_job]
    processor.summarize.side_effect = [
        BiddingSummaryGenerateError("rate limited", retryable=True),
        completed_callback,
    ]
    spring_client.send_summary_callback.side_effect = [
        _callback_response(True, "PENDING"),
        _callback_response(True, "COMPLETED"),
    ]

    worker._handle_message(MESSAGE_ID, _raw_payload())
    worker._handle_message(
        "message-2",
        _raw_payload(second_attempt_id, retry_count=1),
    )

    first_callback = spring_client.send_summary_callback.call_args_list[0].args[1]
    second_callback = spring_client.send_summary_callback.call_args_list[1].args[1]
    assert first_callback.attempt_id == ATTEMPT_ID
    assert first_callback.summary_status == "FAILED"
    assert first_callback.retryable is True
    assert second_callback.attempt_id == second_attempt_id
    assert second_callback.summary_status == "COMPLETED"
    assert second_callback.retryable is False
    assert redis_client.xack.call_count == 2


def test_handle_message_acks_idempotent_callback_rejection():
    worker, redis_client, spring_client, processor = _worker_with_fakes()
    spring_client.get_summary_job.return_value = _job()
    processor.summarize.return_value = _completed_callback()
    spring_client.send_summary_callback.return_value = _callback_response(False)

    worker._handle_message(MESSAGE_ID, _raw_payload())

    redis_client.xack.assert_called_once()


def test_handle_message_acks_invalid_message():
    worker, redis_client, _, _ = _worker_with_fakes()

    worker._handle_message(MESSAGE_ID, {"summaryId": "invalid"})

    redis_client.xack.assert_called_once()


def _worker_with_fakes():
    settings = Settings(_env_file=None, gemini_api_key="test-key")
    redis_client = Mock()
    spring_client = Mock()
    processor = Mock()
    worker = BidNoticeSummaryRedisWorker(
        settings,
        redis_client=redis_client,
        spring_client=spring_client,
        processor=processor,
    )
    return worker, redis_client, spring_client, processor


def _raw_payload(
    attempt_id: str = ATTEMPT_ID,
    retry_count: int = 0,
) -> dict[str, object]:
    return {
        "summaryId": SUMMARY_ID,
        "companyId": 10,
        "attemptId": attempt_id,
        "retryCount": retry_count,
    }


def _job(attempt_id: str = ATTEMPT_ID) -> BidNoticeSummaryJob:
    return BidNoticeSummaryJob(
        summaryId=SUMMARY_ID,
        companyId=10,
        attemptId=attempt_id,
        prompt="금액과 일정을 요약해줘.",
        notice={
            "noticeId": 317,
            "noticeName": "스마트시티 통합관제 플랫폼 구축 용역",
            "noticeType": "SERVICE",
            "attachments": [],
        },
    )


def _completed_callback(
    attempt_id: str = ATTEMPT_ID,
) -> BidNoticeSummaryCallbackRequest:
    return BidNoticeSummaryCallbackRequest(
        attemptId=attempt_id,
        summaryStatus="COMPLETED",
        overviewSummary="스마트시티 통합관제 플랫폼 구축 용역입니다.",
        errorMessage=None,
    )


def _callback_response(
    accepted: bool,
    status: str = "COMPLETED",
) -> BidNoticeSummaryCallbackResponse:
    return BidNoticeSummaryCallbackResponse(
        accepted=accepted,
        summaryId=SUMMARY_ID,
        summaryStatus=status,
        reason=None if accepted else "attempt_mismatch_or_already_finished",
    )
