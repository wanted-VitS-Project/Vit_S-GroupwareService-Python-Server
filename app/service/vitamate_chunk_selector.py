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
        # 빈 excerpt를 제외하고 문서당/전체 최대 개수를 제한합니다.
        selected: list[SelectedVitamateChunk] = []

        for document in job.documents:
            document_count = 0

            for chunk in document.chunks:
                if len(selected) >= MAX_TOTAL_CHUNKS:
                    return selected

                if document_count >= MAX_CHUNKS_PER_DOCUMENT:
                    break

                excerpt = (chunk.excerpt or "").strip()
                if not excerpt:
                    continue

                selected.append(
                    SelectedVitamateChunk(
                        document=document,
                        chunk=chunk,
                        excerpt=excerpt[:MAX_EXCERPT_LENGTH],
                    )
                )
                document_count += 1

        return selected
