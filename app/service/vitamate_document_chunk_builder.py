import re

from app.client.dto import VitamateDocumentChunkRequest, VitamateDocumentChunkSaveRequest
from app.service.extractor.document_text_extractor import ExtractedTextPage


class VitamateDocumentChunkBuilder:
    # 추출된 문서 텍스트를 Spring document_chunk 저장 요청으로 변환합니다.

    MAX_EXCERPT_LENGTH = 900
    MAX_SECTION_TITLE_LENGTH = 255
    MAX_CHUNK_COUNT = 500

    def build(self, pages: list[ExtractedTextPage]) -> VitamateDocumentChunkSaveRequest:
        chunks: list[VitamateDocumentChunkRequest] = []

        for page in pages:
            normalized_text = self._normalize_text(page.text)
            if not normalized_text:
                continue

            for start_offset, end_offset, excerpt in self._split_text(normalized_text):
                if len(chunks) >= self.MAX_CHUNK_COUNT:
                    break

                chunks.append(
                    VitamateDocumentChunkRequest(
                        chunkIndex=len(chunks),
                        pageNumber=page.page_number,
                        sectionTitle=self._trim_section_title(page.section_title),
                        startOffset=start_offset,
                        endOffset=end_offset,
                        tokenCount=self._estimate_token_count(excerpt),
                        excerpt=excerpt,
                    )
                )

            if len(chunks) >= self.MAX_CHUNK_COUNT:
                break

        return VitamateDocumentChunkSaveRequest(chunks=chunks)

    def _normalize_text(self, text: str) -> str:
        # 과도한 공백을 줄여 chunk 저장과 AI 입력을 안정화합니다.
        return re.sub(r"\s+", " ", text).strip()

    def _split_text(self, text: str) -> list[tuple[int, int, str]]:
        # Spring의 excerpt 1000자 제한보다 작게 잘라 안전하게 저장합니다.
        result: list[tuple[int, int, str]] = []
        start = 0

        while start < len(text):
            end = min(start + self.MAX_EXCERPT_LENGTH, len(text))
            excerpt = text[start:end].strip()

            if excerpt:
                result.append((start, end, excerpt))

            start = end

        return result

    def _trim_section_title(self, section_title: str | None) -> str | None:
        # Spring sectionTitle 255자 제한에 맞춥니다.
        if not section_title:
            return None

        trimmed = section_title.strip()
        return trimmed[: self.MAX_SECTION_TITLE_LENGTH] if trimmed else None

    def _estimate_token_count(self, excerpt: str) -> int:
        # 정확한 토큰 계산 전까지 문서 길이 기반의 보수적 추정값을 저장합니다.
        return max(1, len(excerpt) // 3)