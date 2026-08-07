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
        review_templates_text = self.build_review_templates_text(job)

        return build_rfp_analysis_prompt(
            review_type=job.review_type,
            review_templates_text=review_templates_text,
            additional_instruction=job.additional_instruction,
            chunks_text=chunks_text,
        )

    def build_review_templates_text(self, job: VitamateAnalysisJob) -> str:
        # Spring이 내려준 요청 시점 템플릿을 카테고리별 검토 기준으로 정리합니다.
        if not job.review_templates:
            return "등록된 검토 템플릿이 없습니다. 사용자 추가 요청과 문서 chunk만 기준으로 검토합니다."

        lines: list[str] = []
        for template in job.review_templates:
            lines.append(
                "\n".join(
                    [
                        (
                            f"[{template.category_code}] {template.category_name} "
                            f"(version={template.template_version})"
                        ),
                        template.prompt_template,
                    ]
                )
            )

        return "\n\n".join(lines)

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
