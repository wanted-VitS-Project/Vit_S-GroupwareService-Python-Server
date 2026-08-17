from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.client.dto import (
    VitamateChunkEmbeddingRequest,
    VitamateChunkEmbeddingSaveRequest,
    VitamateDocumentChunkRequest,
    VitamateDocumentChunkSaveRequest,
    VitamateDocumentChunkSaveResponse,
    VitamateFileIndexCallbackResponse,
    VitamateFileIndexSourceResponse,
    VitamateSavedDocumentChunk,
)
from app.core.exceptions import (
    SpringVitamateJobNotFoundError,
    SpringVitamateTemporaryError,
    VitamateAiGenerateError,
)
from app.service.extractor.document_text_extractor import ExtractedTextPage
from app.worker.vitamate_file_index_worker import VitamateFileIndexRedisWorker


FILE_VERSION_ID = 900001
MESSAGE_ID = "file-index-message-1"
INDEX_ATTEMPT_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_handle_message_sends_processing_and_completed_callbacks_then_acks():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.return_value = _response("COMPLETED")
    worker._process_file_index.return_value = INDEX_ATTEMPT_ID

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_statuses = [
        call.kwargs["callback"].index_status
        for call in spring_client.send_file_index_callback.call_args_list
    ]
    assert sent_statuses == ["PROCESSING", "COMPLETED"]
    assert spring_client.send_file_index_callback.call_args_list[1].kwargs["callback"].index_attempt_id == INDEX_ATTEMPT_ID
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_sends_failed_callback_when_processing_crashes_then_acks():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.side_effect = [_response("PROCESSING"), _response("FAILED")]
    worker._process_file_index.side_effect = RuntimeError("indexing failed")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_statuses = [
        call.kwargs["callback"].index_status
        for call in spring_client.send_file_index_callback.call_args_list
    ]
    assert sent_statuses == ["PROCESSING", "FAILED"]
    assert spring_client.send_file_index_callback.call_args_list[1].kwargs["callback"].index_attempt_id == INDEX_ATTEMPT_ID
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_marks_retryable_when_gemini_rate_limited():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.side_effect = [_response("PROCESSING"), _response("FAILED")]
    worker._process_file_index.side_effect = VitamateAiGenerateError("Gemini rate limit exceeded", retryable=True)

    worker._handle_message(MESSAGE_ID, _raw_payload())

    failed_callback = spring_client.send_file_index_callback.call_args_list[1].kwargs["callback"]
    assert failed_callback.index_status == "FAILED"
    assert failed_callback.retryable is True
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_marks_not_retryable_for_permanent_ai_error():
    worker, spring_client, ack = _worker_with_fakes()
    spring_client.send_file_index_callback.side_effect = [_response("PROCESSING"), _response("FAILED")]
    worker._process_file_index.side_effect = VitamateAiGenerateError("Gemini returned empty embedding")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    failed_callback = spring_client.send_file_index_callback.call_args_list[1].kwargs["callback"]
    assert failed_callback.retryable is False
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


def test_process_file_index_downloads_extracts_builds_and_saves_chunks():
    worker, spring_client, downloader, extractor_registry, chunk_builder, chunk_embedding_service = _worker_for_process_file_index()
    source = _index_source()
    downloaded_file = Path("rfp.pdf")
    extracted_pages = [
        ExtractedTextPage(
            page_number=1,
            section_title="page-1",
            text="핵심 요구사항과 위험 요소입니다.",
        )
    ]
    chunk_request = _chunk_save_request()

    spring_client.get_file_index_source.return_value = source
    downloader.download.side_effect = lambda actual_source: _downloaded_file(
        actual_source,
        source,
        downloaded_file,
    )
    extractor_registry.extract.return_value = extracted_pages
    chunk_builder.build.return_value = chunk_request
    spring_client.save_document_chunks.return_value = VitamateDocumentChunkSaveResponse(
        fileVersionId=FILE_VERSION_ID,
        indexAttemptId=INDEX_ATTEMPT_ID,
        savedChunkCount=1,
        savedChunks=[
            VitamateSavedDocumentChunk(
                documentChunkId=990001,
                chunkIndex=0,
                embeddingStatus="PENDING",
            )
        ],
    )
    embedding_request = VitamateChunkEmbeddingSaveRequest(
        embeddingModel="gemini-embedding-001",
        indexAttemptId=INDEX_ATTEMPT_ID,
        chunks=[
            VitamateChunkEmbeddingRequest(
                documentChunkId=990001,
                chromaId=f"vitamate:{FILE_VERSION_ID}:990001:{INDEX_ATTEMPT_ID}",
            )
        ],
    )
    chunk_embedding_service.embed_and_store.return_value = embedding_request

    index_attempt_id = worker._process_file_index(FILE_VERSION_ID)

    assert index_attempt_id == INDEX_ATTEMPT_ID
    spring_client.get_file_index_source.assert_called_once_with(FILE_VERSION_ID)
    downloader.download.assert_called_once_with(source)
    extractor_registry.extract.assert_called_once_with(
        file_path=downloaded_file,
        extension="pdf",
        mime_type="application/pdf",
    )
    chunk_builder.build.assert_called_once_with(extracted_pages)
    spring_client.save_document_chunks.assert_called_once_with(
        file_version_id=FILE_VERSION_ID,
        request=chunk_request,
    )
    chunk_embedding_service.embed_and_store.assert_called_once_with(
        file_version_id=FILE_VERSION_ID,
        index_attempt_id=INDEX_ATTEMPT_ID,
        saved_chunks=spring_client.save_document_chunks.return_value.saved_chunks,
        original_chunks=chunk_request.chunks,
    )
    spring_client.save_chunk_embeddings.assert_called_once_with(
        file_version_id=FILE_VERSION_ID,
        request=embedding_request,
    )


def test_process_file_index_rejects_empty_chunks():
    worker, spring_client, downloader, extractor_registry, chunk_builder, chunk_embedding_service = _worker_for_process_file_index()
    source = _index_source()
    downloaded_file = Path("empty.pdf")

    spring_client.get_file_index_source.return_value = source
    downloader.download.side_effect = lambda actual_source: _downloaded_file(
        actual_source,
        source,
        downloaded_file,
    )
    extractor_registry.extract.return_value = []
    chunk_builder.build.return_value = VitamateDocumentChunkSaveRequest(chunks=[])

    with pytest.raises(ValueError, match="No extractable text chunks"):
        worker._process_file_index(FILE_VERSION_ID)

    spring_client.save_document_chunks.assert_not_called()
    chunk_embedding_service.embed_and_store.assert_not_called()


def test_replace_temporary_section_title_uses_original_file_name():
    worker = VitamateFileIndexRedisWorker.__new__(VitamateFileIndexRedisWorker)
    pages = [
        ExtractedTextPage(
            page_number=1,
            section_title="tmpabc123.csv",
            text="테스트 문서 본문",
        ),
        ExtractedTextPage(
            page_number=2,
            section_title="Sheet1",
            text="엑셀 시트 본문",
        ),
    ]

    replaced = worker._replace_temporary_section_title(
        pages=pages,
        temporary_file_name="tmpabc123.csv",
        original_file_name="vitamate-test-900001.csv",
    )

    assert replaced[0].section_title == "vitamate-test-900001.csv"
    assert replaced[1].section_title == "Sheet1"


def _worker_with_fakes():
    # Redis 연결 없이 파일 인덱싱 worker 처리 흐름만 검증합니다.
    worker = VitamateFileIndexRedisWorker.__new__(VitamateFileIndexRedisWorker)
    spring_client = Mock()
    ack = Mock()
    worker._process_file_index = Mock()
    worker._spring_client = spring_client
    worker._ack = ack

    return worker, spring_client, ack


def _worker_for_process_file_index():
    # Redis 없이 실제 파일 인덱싱 처리 흐름의 협력 객체 호출 순서를 검증합니다.
    worker = VitamateFileIndexRedisWorker.__new__(VitamateFileIndexRedisWorker)
    spring_client = Mock()
    downloader = Mock()
    extractor_registry = Mock()
    chunk_builder = Mock()
    chunk_embedding_service = Mock()

    worker._spring_client = spring_client
    worker._file_downloader = downloader
    worker._extractor_registry = extractor_registry
    worker._chunk_builder = chunk_builder
    worker._chunk_embedding_service = chunk_embedding_service

    return worker, spring_client, downloader, extractor_registry, chunk_builder, chunk_embedding_service


@contextmanager
def _downloaded_file(actual_source, expected_source, downloaded_file):
    # downloader context manager가 넘겨주는 임시 파일 경로를 테스트용으로 대체합니다.
    assert actual_source == expected_source
    yield downloaded_file


def _raw_payload() -> dict[str, object]:
    return {
        "fileVersionId": FILE_VERSION_ID,
        "retryCount": 0,
    }


def _response(index_status: str) -> VitamateFileIndexCallbackResponse:
    return VitamateFileIndexCallbackResponse(
        accepted=True,
        fileVersionId=FILE_VERSION_ID,
        indexAttemptId=INDEX_ATTEMPT_ID,
        indexStatus=index_status,
        reason=None,
    )


def _index_source() -> VitamateFileIndexSourceResponse:
    return VitamateFileIndexSourceResponse(
        fileVersionId=FILE_VERSION_ID,
        fileId=900001,
        projectId=900001,
        originalFileName="rfp.pdf",
        extension="pdf",
        mimeType="application/pdf",
        sizeBytes=1024,
        storageKey="local/test/rfp.pdf",
        downloadUrl="https://example.test/rfp.pdf",
    )


def _chunk_save_request() -> VitamateDocumentChunkSaveRequest:
    return VitamateDocumentChunkSaveRequest(
        chunks=[
            VitamateDocumentChunkRequest(
                chunkIndex=0,
                pageNumber=1,
                sectionTitle="page-1",
                startOffset=0,
                endOffset=20,
                tokenCount=7,
                excerpt="핵심 요구사항과 위험 요소입니다.",
            )
        ]
    )
