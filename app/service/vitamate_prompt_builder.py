from app.client.dto import VitamateAnalysisJob
from app.prompt.vitamate_rfp_analysis_prompt import build_rfp_analysis_prompt
from app.service.vitamate_chunk_selector import SelectedVitamateChunk, VitamateChunkSelector


class VitamatePromptBuilder:
    # 분석 작업을 기준 문서와 대상 문서가 분리된 Gemini 프롬프트로 변환합니다.

    def __init__(self, chunk_selector: VitamateChunkSelector | None = None):
        self._chunk_selector = chunk_selector or VitamateChunkSelector()

    def build(self, job: VitamateAnalysisJob) -> str:
        selected_chunks = self._chunk_selector.select(job)
        return self.build_with_selected_chunks(job, selected_chunks)

    def build_with_selected_chunks(self, job: VitamateAnalysisJob, selected_chunks: list[SelectedVitamateChunk]) -> str:
        return build_rfp_analysis_prompt(
            review_type=job.review_type,
            review_templates_text=self.build_review_templates_text(job),
            user_prompt=job.prompt,
            reference_chunks_text=self.build_chunks_text(selected_chunks, "REFERENCE"),
            target_chunks_text=self.build_chunks_text(selected_chunks, "TARGET"),
        )

    def build_review_templates_text(self, job: VitamateAnalysisJob) -> str:
        # 요청 당시 저장된 템플릿 스냅샷을 보조 검토 항목으로 조립합니다.
        if not job.review_templates:
            return "등록된 서비스 검토 항목 없음"
        return "\n\n".join(
            "\n".join([
                f"[{template.category_code}] {template.category_name} (version={template.template_version})",
                template.prompt_template,
            ])
            for template in job.review_templates
        )

    def build_chunks_text(self, selected_chunks: list[SelectedVitamateChunk], document_role: str) -> str:
        # 지정한 역할의 청크만 문서명과 출처 식별자를 포함해 변환합니다.
        lines: list[str] = []
        current_file_version_id: int | None = None
        for selected in selected_chunks:
            document = selected.document
            chunk = selected.chunk
            if document.document_role != document_role:
                continue
            if current_file_version_id != document.file_version_id:
                lines.append(
                    f"[문서 역할={document_role}] {document.file_name} (fileVersionId={document.file_version_id})"
                )
                current_file_version_id = document.file_version_id
            lines.append(f"- chunkId={chunk.document_chunk_id}, page={chunk.page_number}: {selected.excerpt}")
        return "\n".join(lines) or "선택된 문서 청크 없음"
