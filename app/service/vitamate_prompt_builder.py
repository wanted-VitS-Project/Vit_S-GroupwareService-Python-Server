from app.client.dto import VitamateAnalysisJob
from app.prompt.vitamate_rfp_analysis_prompt import build_rfp_analysis_prompt
from app.service.vitamate_chunk_selector import SelectedVitamateChunk, VitamateChunkSelector


class VitamatePromptBuilder:
    # 비타메이트 분석 요청을 Gemini 프롬프트로 변환합니다.

    def __init__(self, chunk_selector: VitamateChunkSelector | None = None):
        self._chunk_selector = chunk_selector or VitamateChunkSelector()

    def build(self, job: VitamateAnalysisJob) -> str:
        # selector가 고른 chunk를 RFP 분석 템플릿에 주입합니다.
        selected_chunks = self._chunk_selector.select(job)
        return self.build_with_selected_chunks(job, selected_chunks)

    def build_with_selected_chunks(
        self,
        job: VitamateAnalysisJob,
        selected_chunks: list[SelectedVitamateChunk],
    ) -> str:
        # 이미 선택된 chunk 목록을 사용해 프롬프트와 citation 근거를 일치시킵니다.
        chunks_text = self.build_chunks_text(selected_chunks)

        return build_rfp_analysis_prompt(
            user_prompt=job.prompt,
            chunks_text=chunks_text,
        )

    def build_chunks_text(self, selected_chunks: list[SelectedVitamateChunk]) -> str:
        # selector가 고른 chunk만 Gemini 입력 텍스트로 변환합니다.
        lines: list[str] = []
        current_file_version_id: int | None = None

        for selected in selected_chunks:
            document = selected.document
            chunk = selected.chunk

            if current_file_version_id != document.file_version_id:
                lines.append(f"[문서] {document.file_name} (fileVersionId={document.file_version_id})")
                current_file_version_id = document.file_version_id

            lines.append(
                f"- chunkId={chunk.document_chunk_id}, page={chunk.page_number}: {selected.excerpt}"
            )

        return "\n".join(lines)
