from unittest.mock import Mock

from app.client.dto import VitamateFileIndexCallbackResponse
from app.core.exceptions import (
    SpringVitamateJobNotFoundError,
    SpringVitamateTemporaryError,
)
from app.worker.vitamate_file_index_worker import VitamateFileIndexRedisWorker


FILE_VERSION_ID = 900001
MESSAGE_ID = "file-index-message-1"


def test_handle_message_sends_processing_and_completed_callbacks_then_acks():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.return_value = _response("COMPLETED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_statuses = [
        call.kwargs["callback"].index_status
        for call in spring_client.send_file_index_callback.call_args_list
    ]
    assert sent_statuses == ["PROCESSING", "COMPLETED"]
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_sends_failed_callback_when_processing_crashes_then_acks():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.side_effect = [
        _response("PROCESSING"),
        RuntimeError("indexing failed"),
        _response("FAILED"),
    ]

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_statuses = [
        call.kwargs["callback"].index_status
        for call in spring_client.send_file_index_callback.call_args_list
    ]
    assert sent_statuses == ["PROCESSING", "COMPLETED", "FAILED"]
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_does_not_ack_when_spring_has_temporary_failure():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.side_effect = SpringVitamateTemporaryError("temporary")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    ack.assert_not_called()


def test_handle_message_acks_when_file_version_is_not_found():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.side_effect = SpringVitamateJobNotFoundError("not found")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_acks_invalid_message():
    worker, _, ack = _worker_with_fakes()

    worker._handle_message(MESSAGE_ID, {"fileVersionId": "invalid"})

    ack.assert_called_once_with(MESSAGE_ID)


def _worker_with_fakes():
    # Redis 연결 없이 파일 인덱싱 worker 처리 흐름만 검증합니다.
    worker = VitamateFileIndexRedisWorker.__new__(VitamateFileIndexRedisWorker)
    spring_client = Mock()
    ack = Mock()

    worker._spring_client = spring_client
    worker._ack = ack

    return worker, spring_client, ack


def _raw_payload() -> dict[str, object]:
    return {
        "fileVersionId": FILE_VERSION_ID,
        "retryCount": 0,
    }


def _response(index_status: str) -> VitamateFileIndexCallbackResponse:
    return VitamateFileIndexCallbackResponse(
        accepted=True,
        fileVersionId=FILE_VERSION_ID,
        indexStatus=index_status,
        reason=None,
    )
