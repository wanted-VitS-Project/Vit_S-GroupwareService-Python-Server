import logging
import time
from dataclasses import replace
from typing import Any

import redis
from app.service.extractor.extractor_registry import ExtractorRegistry
from app.service.vitamate_document_chunk_builder import VitamateDocumentChunkBuilder
from app.service.vitamate_file_downloader import VitamateFileDownloader
from app.client.dto import (
    VitamateChunkEmbeddingRequest,
    VitamateChunkEmbeddingSaveRequest,
    VitamateFileIndexCallbackRequest,
    VitamateFileIndexCallbackResponse,
)
from app.client.spring_vitamate_client import SpringVitamateClient
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    SpringVitamateAuthError,
    SpringVitamateBadRequestError,
    SpringVitamateJobNotFoundError,
    SpringVitamateTemporaryError,
)
from app.service.extractor.document_text_extractor import ExtractedTextPage
from app.worker.message import VitamateFileIndexJobMessage

logger = logging.getLogger(__name__)


class VitamateFileIndexRedisWorker:
    # Redis Stream에서 파일 인덱싱 작업을 받아 Spring file_index 상태를 갱신합니다.

    def __init__(self, settings: Settings):
        self._settings = settings
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self._spring_client = SpringVitamateClient(settings)
        self._file_downloader = VitamateFileDownloader()
        self._extractor_registry = ExtractorRegistry()
        self._chunk_builder = VitamateDocumentChunkBuilder()

    def run_forever(self) -> None:
        # worker를 계속 실행하며 파일 인덱싱 메시지를 소비합니다.
        self._ensure_consumer_group()

        logger.info(
            "Vitamate file index worker started stream=%s group=%s consumer=%s",
            self._settings.vitamate_file_index_stream_key,
            self._settings.vitamate_file_index_consumer_group,
            self._settings.vitamate_file_index_consumer_name,
        )

        while True:
            self.consume_once(block_ms=5000)

    def consume_once(self, block_ms: int = 5000) -> None:
        # 파일 인덱싱 메시지를 한 번 읽고 처리합니다.
        self._ensure_consumer_group()

        messages = self._redis.xreadgroup(
            groupname=self._settings.vitamate_file_index_consumer_group,
            consumername=self._settings.vitamate_file_index_consumer_name,
            streams={self._settings.vitamate_file_index_stream_key: ">"},
            count=1,
            block=block_ms,
        )

        if not messages:
            return

        for _, stream_messages in messages:
            for message_id, raw_payload in stream_messages:
                self._handle_message(message_id, raw_payload)

    def _handle_message(self, message_id: str, raw_payload: dict[str, Any]) -> None:
        # 메시지를 검증하고 PROCESSING, COMPLETED 상태 callback을 전송합니다.
        try:
            message = VitamateFileIndexJobMessage.model_validate(raw_payload)
        except Exception:
            logger.exception("Invalid Vitamate file index message messageId=%s", message_id)
            self._ack(message_id)
            return

        logger.info(
            "Vitamate file index job received fileVersionId=%s retryCount=%s",
            message.file_version_id,
            message.retry_count,
        )

        index_attempt_id: str | None = None

        try:
            processing_response = self._send_callback(message.file_version_id, "PROCESSING", None)
            index_attempt_id = processing_response.index_attempt_id

            index_attempt_id = self._process_file_index(message.file_version_id)

            self._send_callback(message.file_version_id, "COMPLETED", None, index_attempt_id)

        except SpringVitamateAuthError:
            logger.exception(
                "Vitamate file index callback auth failed fileVersionId=%s",
                message.file_version_id,
            )
            time.sleep(5)
            return
        except SpringVitamateTemporaryError:
            logger.exception(
                "Temporary Spring file index callback failure fileVersionId=%s",
                message.file_version_id,
            )
            time.sleep(5)
            return
        except SpringVitamateBadRequestError:
            logger.exception(
                "Spring rejected file index callback fileVersionId=%s",
                message.file_version_id,
            )
            self._ack(message_id)
            return
        except SpringVitamateJobNotFoundError:
            logger.warning(
                "Vitamate file index job ignored fileVersionId=%s reason=not_found_or_stale",
                message.file_version_id,
            )
            self._ack(message_id)
            return
        except Exception:
            logger.exception(
                "Vitamate file index processing failed fileVersionId=%s",
                message.file_version_id,
            )

            if self._try_failed_callback(message.file_version_id, index_attempt_id):
                self._ack(message_id)
            return

        logger.info(
            "Vitamate file index job completed fileVersionId=%s",
            message.file_version_id,
        )
        self._ack(message_id)

    def _process_file_index(self, file_version_id: int) -> str:
        # Spring에서 파일 정보를 조회하고, 파일 텍스트를 chunk와 임베딩 결과로 저장합니다.
        source = self._spring_client.get_file_index_source(file_version_id)

        with self._file_downloader.download(source) as file_path:
            pages = self._extractor_registry.extract(
                file_path=file_path,
                extension=source.extension,
                mime_type=source.mime_type,
            )
            pages = self._replace_temporary_section_title(
                pages=pages,
                temporary_file_name=file_path.name,
                original_file_name=source.original_file_name,
            )

        chunk_request = self._chunk_builder.build(pages)

        if not chunk_request.chunks:
            raise ValueError("No extractable text chunks")

        response = self._spring_client.save_document_chunks(
            file_version_id=file_version_id,
            request=chunk_request,
        )

        logger.info(
            "Vitamate document chunks saved fileVersionId=%s indexAttemptId=%s savedChunkCount=%s",
            response.file_version_id,
            response.index_attempt_id,
            response.saved_chunk_count,
        )

        embedding_request = VitamateChunkEmbeddingSaveRequest(
            embeddingModel="local-placeholder",
            indexAttemptId=response.index_attempt_id,
            chunks=[
                VitamateChunkEmbeddingRequest(
                    documentChunkId=chunk.document_chunk_id,
                    chromaId=f"vitamate:document-chunk:{chunk.document_chunk_id}",
                )
                for chunk in response.saved_chunks
            ],
        )

        self._spring_client.save_chunk_embeddings(
            file_version_id=file_version_id,
            request=embedding_request,
        )

        logger.info(
            "Vitamate document chunk embeddings saved fileVersionId=%s indexAttemptId=%s chunkCount=%s",
            response.file_version_id,
            response.index_attempt_id,
            len(response.saved_chunks),
        )

        return response.index_attempt_id

    def _replace_temporary_section_title(
        self,
        pages: list[ExtractedTextPage],
        temporary_file_name: str,
        original_file_name: str,
    ) -> list[ExtractedTextPage]:
        # 임시 파일명이 DB에 남지 않도록 원본 파일명으로 보정합니다.
        return [
            replace(page, section_title=original_file_name)
            if page.section_title == temporary_file_name
            else page
            for page in pages
        ]
    
    def _send_callback(
        self,
        file_version_id: int,
        index_status: str,
        error_message: str | None,
        index_attempt_id: str | None = None,
    ) -> VitamateFileIndexCallbackResponse:
        # 파일 인덱싱 상태를 Spring에 전달합니다.
        response = self._spring_client.send_file_index_callback(
            file_version_id=file_version_id,
            callback=VitamateFileIndexCallbackRequest(
                indexStatus=index_status,
                indexAttemptId=index_attempt_id,
                errorMessage=error_message,
            ),
        )

        logger.info(
            "Vitamate file index callback completed fileVersionId=%s indexAttemptId=%s accepted=%s status=%s",
            response.file_version_id,
            response.index_attempt_id,
            response.accepted,
            response.index_status,
        )

        return response

    def _try_failed_callback(self, file_version_id: int, index_attempt_id: str | None) -> bool:
        # 처리 실패 상태를 Spring에 저장해 인덱싱 상태가 멈추지 않게 합니다.
        if not index_attempt_id:
            logger.warning(
                "Vitamate file index failed before indexAttemptId was issued fileVersionId=%s",
                file_version_id,
            )
            return True

        try:
            self._send_callback(file_version_id, "FAILED", "File indexing failed", index_attempt_id)
            return True
        except Exception:
            logger.exception(
                "Vitamate file index failed callback rejected fileVersionId=%s indexAttemptId=%s",
                file_version_id,
                index_attempt_id,
            )
            return False

    def _ensure_consumer_group(self) -> None:
        # Redis Stream consumer group이 없으면 생성합니다.
        try:
            self._redis.xgroup_create(
                name=self._settings.vitamate_file_index_stream_key,
                groupname=self._settings.vitamate_file_index_consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _ack(self, message_id: str) -> None:
        # 처리 완료된 메시지를 Redis Stream에서 ack 처리합니다.
        self._redis.xack(
            self._settings.vitamate_file_index_stream_key,
            self._settings.vitamate_file_index_consumer_group,
            message_id,
        )


def main() -> None:
    # CLI에서 파일 인덱싱 worker를 실행하기 위한 진입점입니다.
    logging.basicConfig(level=logging.INFO)
    worker = VitamateFileIndexRedisWorker(get_settings())
    worker.run_forever()


if __name__ == "__main__":
    main()
