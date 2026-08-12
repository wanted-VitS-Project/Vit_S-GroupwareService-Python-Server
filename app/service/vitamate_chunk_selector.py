from dataclasses import dataclass

from app.client.dto import VitamateAnalysisJob, VitamateChunk, VitamateDocument


MAX_CHUNKS_PER_DOCUMENT = 5
MAX_TOTAL_CHUNKS = 15
MAX_EXCERPT_LENGTH = 1200


@dataclass(frozen=True)
class SelectedVitamateChunk:
    # 프롬프트 입력과 citation 저장에 함께 사용할 선택 chunk입니다.
    document: VitamateDocument
    chunk: VitamateChunk
    excerpt: str


class VitamateChunkSelector:
    # 비타메이트 분석에 사용할 문서 chunk를 일관된 정책으로 선택합니다.

    def select(self, job: VitamateAnalysisJob) -> list[SelectedVitamateChunk]:
        # 비교 분석에 필요한 기준/대상 문서를 먼저 한 건씩 확보한 뒤 나머지 chunk를 채웁니다.
        selected: list[SelectedVitamateChunk] = []
        selected_keys: set[tuple[int, int]] = set()
        document_counts: dict[int, int] = {}

        for role in ("REFERENCE", "TARGET"):
            representative = self._find_first_selectable_chunk(job, role)
            if representative is not None:
                selected.append(representative)
                selected_keys.add(self._key(representative.document, representative.chunk))
                document_counts[representative.document.file_version_id] = 1

        for document in job.documents:
            document_count = document_counts.get(document.file_version_id, 0)

            for chunk in document.chunks:
                if len(selected) >= MAX_TOTAL_CHUNKS:
                    return selected

                if document_count >= MAX_CHUNKS_PER_DOCUMENT:
                    break

                excerpt = (chunk.excerpt or "").strip()
                if not excerpt or self._key(document, chunk) in selected_keys:
                    continue

                selected_chunk = SelectedVitamateChunk(
                    document=document,
                    chunk=chunk,
                    excerpt=excerpt[:MAX_EXCERPT_LENGTH],
                )
                selected.append(selected_chunk)
                selected_keys.add(self._key(document, chunk))
                document_count += 1

        return selected

    def _find_first_selectable_chunk(
        self,
        job: VitamateAnalysisJob,
        document_role: str,
    ) -> SelectedVitamateChunk | None:
        # 지정한 역할에서 내용이 있는 첫 chunk를 대표 입력으로 선택합니다.
        for document in job.documents:
            if document.document_role != document_role:
                continue
            for chunk in document.chunks:
                excerpt = (chunk.excerpt or "").strip()
                if excerpt:
                    return SelectedVitamateChunk(
                        document=document,
                        chunk=chunk,
                        excerpt=excerpt[:MAX_EXCERPT_LENGTH],
                    )
        return None

    def _key(self, document: VitamateDocument, chunk: VitamateChunk) -> tuple[int, int]:
        # 대표 선택과 일반 선택에서 같은 chunk가 중복되지 않도록 식별키를 만듭니다.
        return document.file_version_id, chunk.document_chunk_id
