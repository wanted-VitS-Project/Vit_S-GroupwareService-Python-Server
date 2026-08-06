from app.client.dto import VitamateAnalysisJob
from app.prompt.vitamate_rfp_analysis_prompt import build_rfp_analysis_prompt


class VitamatePromptBuilder:
    # 비타메이트 분석 요청을 Gemini 프롬프트로 변환합니다.

    def build(self, job: VitamateAnalysisJob) -> str:
        # 사용자 요청과 선택 문서 chunk를 RFP 분석 템플릿에 주입합니다.
        chunks_text = self._build_chunks_text(job)
        return build_rfp_analysis_prompt(
            user_prompt=job.prompt,
            chunks_text=chunks_text,
        )

    def _build_chunks_text(self, job: VitamateAnalysisJob) -> str:
        # 선택 문서의 chunk excerpt만 AI 입력으로 사용합니다.
        lines: list[str] = []

        for document in job.documents:
            lines.append(f"[문서] {document.file_name} (fileVersionId={document.file_version_id})")

            for chunk in document.chunks[:5]:
                excerpt = chunk.excerpt or ""
                if not excerpt.strip():
                    continue

                lines.append(
                    f"- chunkId={chunk.document_chunk_id}, page={chunk.page_number}: {excerpt[:1200]}"
                )

        return "\n".join(lines)