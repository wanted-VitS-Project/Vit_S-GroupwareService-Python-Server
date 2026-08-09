from unittest.mock import Mock

from app.client.dto import VitamateChromaCleanupCallbackResponse
from app.worker.vitamate_chroma_cleanup_worker import (
    VitamateChromaCleanupRedisWorker,
)


MESSAGE_ID = "cleanup-message-1"
CLEANUP_JOB_ID = 1
ATTEMPT_ID = "e2285327-8be8-4b80-a5f3-f48cf4fb24db"
FILE_VERSION_IDS = [990001, 990002]


def test_completes_cleanup_and_acks_message():
    # 벡터 삭제 성공 시 PROCESSING과 COMPLETED를 전송하고 ACK합니다.
    worker, spring_client, cleanup_service, ack, dlq = _worker_with_fakes()

    spring_client.send_chroma_cleanup_callback.side_effect = [
        _response("PROCESSING"),
        _response("COMPLETED"),
    ]
    cleanup_service.cleanup.return_value = 3

    worker._handle_message(MESSAGE_ID, _raw_payload())

    statuses = [
        call.kwargs["callback"].status
        for call in spring_client.send_chroma_cleanup_callback.call_args_list
    ]

    assert statuses == ["PROCESSING", "COMPLETED"]
    cleanup_service.cleanup.assert_called_once_with(FILE_VERSION_IDS)

    completed_callback = (
        spring_client.send_chroma_cleanup_callback
        .call_args_list[1]
        .kwargs["callback"]
    )
    assert completed_callback.deleted_vector_count == 3

    ack.assert_called_once_with(MESSAGE_ID)
    dlq.assert_not_called()


def test_acks_stale_attempt_without_deleting_vectors():
    # Spring이 오래된 attemptId를 거부하면 ChromaDB를 건드리지 않습니다.
    worker, spring_client, cleanup_service, ack, dlq = _worker_with_fakes()

    spring_client.send_chroma_cleanup_callback.return_value = _response(
        cleanup_status="PUBLISHED",
        accepted=False,
        reason="attempt_mismatch_or_already_finished",
    )

    worker._handle_message(MESSAGE_ID, _raw_payload())

    cleanup_service.cleanup.assert_not_called()
    ack.assert_called_once_with(MESSAGE_ID)
    dlq.assert_not_called()


def test_retryable_failure_is_reported_and_acked():
    # 일시적인 Chroma 장애는 Spring의 재시도 예약 후 현재 메시지를 ACK합니다.
    worker, spring_client, cleanup_service, ack, dlq = _worker_with_fakes()

    spring_client.send_chroma_cleanup_callback.side_effect = [
        _response("PROCESSING"),
        _response("RETRY_WAIT"),
    ]
    cleanup_service.cleanup.side_effect = RuntimeError("Chroma unavailable")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    failed_callback = (
        spring_client.send_chroma_cleanup_callback
        .call_args_list[1]
        .kwargs["callback"]
    )

    assert failed_callback.status == "FAILED"
    assert failed_callback.retryable is True
    assert failed_callback.error_code == "CHROMA_CLEANUP_FAILED"

    ack.assert_called_once_with(MESSAGE_ID)
    dlq.assert_not_called()


def test_dead_letter_failure_is_published_to_dlq_and_acked():
    # 최대 재시도 이후 실패하면 DLQ에 보관하고 현재 메시지를 ACK합니다.
    worker, spring_client, cleanup_service, ack, dlq = _worker_with_fakes()

    spring_client.send_chroma_cleanup_callback.side_effect = [
        _response("PROCESSING"),
        _response("DEAD_LETTER"),
    ]
    cleanup_service.cleanup.side_effect = RuntimeError("Chroma unavailable")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    dlq.assert_called_once()
    ack.assert_called_once_with(MESSAGE_ID)


def test_invalid_message_is_published_to_dlq_and_acked():
    # 필수 필드가 없는 Redis 메시지는 실행하지 않고 DLQ로 격리합니다.
    worker, spring_client, cleanup_service, ack, dlq = _worker_with_fakes()

    worker._handle_message(
        MESSAGE_ID,
        {
            "cleanupJobId": "invalid",
            "fileVersionIds": "[]",
        },
    )

    spring_client.send_chroma_cleanup_callback.assert_not_called()
    cleanup_service.cleanup.assert_not_called()
    worker._publish_invalid_message_to_dlq.assert_called_once_with(MESSAGE_ID)
    ack.assert_called_once_with(MESSAGE_ID)
    dlq.assert_not_called()


def _worker_with_fakes():
    # Redis와 외부 서버 없이 worker의 분기와 호출 순서만 검증합니다.
    worker = VitamateChromaCleanupRedisWorker.__new__(
        VitamateChromaCleanupRedisWorker
    )

    spring_client = Mock()
    cleanup_service = Mock()
    ack = Mock()
    dlq = Mock()

    worker._spring_client = spring_client
    worker._cleanup_service = cleanup_service
    worker._ack = ack
    worker._publish_message_to_dlq = dlq
    worker._publish_invalid_message_to_dlq = Mock()

    return worker, spring_client, cleanup_service, ack, dlq


def _raw_payload() -> dict[str, str]:
    # Spring Outbox가 Redis Stream에 발행하는 형식과 동일하게 구성합니다.
    return {
        "cleanupJobId": str(CLEANUP_JOB_ID),
        "cleanupKey": "cleanup-key-1",
        "attemptId": ATTEMPT_ID,
        "retryCount": "0",
        "fileVersionIds": "[990001, 990002]",
    }


def _response(
    cleanup_status: str,
    accepted: bool = True,
    reason: str | None = None,
) -> VitamateChromaCleanupCallbackResponse:
    # Spring cleanup callback 응답을 테스트용으로 생성합니다.
    return VitamateChromaCleanupCallbackResponse(
        accepted=accepted,
        cleanupJobId=CLEANUP_JOB_ID,
        cleanupStatus=cleanup_status,
        reason=reason,
    )
from unittest.mock import Mock


def test_recovers_stale_pending_message():
    # 오래된 Pending 메시지를 현재 워커가 회수해 다시 처리하는지 검증합니다.
    worker = VitamateChromaCleanupRedisWorker.__new__(
        VitamateChromaCleanupRedisWorker
    )
    worker._redis = Mock()
    worker._settings = Mock(
        vitamate_chroma_cleanup_stream_key="vitamate:chroma-cleanup:jobs",
        vitamate_chroma_cleanup_consumer_group="vitamate-chroma-cleanup-workers",
        vitamate_chroma_cleanup_consumer_name="worker-2",
        vitamate_chroma_cleanup_claim_min_idle_ms=300_000,
        vitamate_chroma_cleanup_claim_count=10,
    )
    worker._claim_cursor = "0-0"
    worker._handle_message = Mock()

    payload = {
        "cleanupJobId": "1",
        "cleanupKey": "cleanup-key",
        "attemptId": "attempt-id",
        "fileVersionIds": "[990001, 990002]",
        "retryCount": "0",
    }
    worker._redis.xautoclaim.return_value = (
        "0-0",
        [("1786264843295-0", payload)],
        [],
    )

    recovered = worker._recover_stale_messages()

    assert recovered is True
    assert worker._claim_cursor == "0-0"
    worker._handle_message.assert_called_once_with(
        "1786264843295-0",
        payload,
    )


def test_returns_false_when_no_stale_pending_message_exists():
    # 회수할 Pending 메시지가 없으면 일반 신규 메시지 소비로 넘어갑니다.
    worker = VitamateChromaCleanupRedisWorker.__new__(
        VitamateChromaCleanupRedisWorker
    )
    worker._redis = Mock()
    worker._settings = Mock(
        vitamate_chroma_cleanup_stream_key="vitamate:chroma-cleanup:jobs",
        vitamate_chroma_cleanup_consumer_group="vitamate-chroma-cleanup-workers",
        vitamate_chroma_cleanup_consumer_name="worker-2",
        vitamate_chroma_cleanup_claim_min_idle_ms=300_000,
        vitamate_chroma_cleanup_claim_count=10,
    )
    worker._claim_cursor = "0-0"
    worker._handle_message = Mock()
    worker._redis.xautoclaim.return_value = ("0-0", [], [])

    recovered = worker._recover_stale_messages()

    assert recovered is False
    worker._handle_message.assert_not_called()