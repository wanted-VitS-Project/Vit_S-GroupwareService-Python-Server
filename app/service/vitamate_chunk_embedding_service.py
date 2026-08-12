from app.client.dto import (
    VitamateChunkEmbeddingRequest,
    VitamateChunkEmbeddingSaveRequest,
    VitamateDocumentChunkRequest,
    VitamateSavedDocumentChunk,
)
from app.client.gemini_embedding_client import GeminiEmbeddingClient
from app.core.config import Settings
from app.service.chroma.vitamate_chroma_store import VitamateChromaStore


class VitamateChunkEmbeddingService:
    # Spring에 저장된 chunk 정보를 기준으로 embedding 생성과 ChromaDB 저장을 처리합니다.

    def __init__(
        self,
        settings: Settings,
        embedding_client: GeminiEmbeddingClient | None = None,
        chroma_store: VitamateChromaStore | None = None,
    ):
        self._settings = settings
        self._embedding_client = embedding_client or GeminiEmbeddingClient(settings)
        self._chroma_store = chroma_store or VitamateChromaStore(settings)

    def embed_and_store(
        self,
        file_version_id: int,
        index_attempt_id: str,
        saved_chunks: list[VitamateSavedDocumentChunk],
        original_chunks: list[VitamateDocumentChunkRequest],
    ) -> VitamateChunkEmbeddingSaveRequest:
        # chunkIndex 기준으로 원문 chunk와 Spring 저장 chunk를 매칭합니다.
        original_by_index = {
            chunk.chunk_index: chunk
            for chunk in original_chunks
        }

        embedding_results: list[VitamateChunkEmbeddingRequest] = []

        for saved_chunk in saved_chunks:
            original_chunk = original_by_index.get(saved_chunk.chunk_index)
            if original_chunk is None:
                continue

            chroma_id = self._build_chroma_id(
                file_version_id=file_version_id,
                document_chunk_id=saved_chunk.document_chunk_id,
                index_attempt_id=index_attempt_id,
            )

            embedding = self._embedding_client.embed_text(original_chunk.excerpt)

            self._chroma_store.upsert_chunk(
                chroma_id=chroma_id,
                embedding=embedding,
                document=original_chunk.excerpt,
                metadata={
                    "fileVersionId": file_version_id,
                    "documentChunkId": saved_chunk.document_chunk_id,
                    "chunkIndex": saved_chunk.chunk_index,
                    "pageNumber": original_chunk.page_number,
                    "sectionTitle": original_chunk.section_title,
                    "indexAttemptId": index_attempt_id,
                },
            )

            embedding_results.append(
                VitamateChunkEmbeddingRequest(
                    documentChunkId=saved_chunk.document_chunk_id,
                    chromaId=chroma_id,
                )
            )

        return VitamateChunkEmbeddingSaveRequest(
            embeddingModel=self._settings.gemini_embedding_model,
            indexAttemptId=index_attempt_id,
            chunks=embedding_results,
        )

    def _build_chroma_id(
        self,
        file_version_id: int,
        document_chunk_id: int,
        index_attempt_id: str,
    ) -> str:
        # 재인덱싱 시도별 vector를 구분하기 위한 ChromaDB ID입니다.
        return f"vitamate:{file_version_id}:{document_chunk_id}:{index_attempt_id}"
