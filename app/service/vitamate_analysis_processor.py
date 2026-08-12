from app.client.dto import (
    VitamateAnalysisJob,
    VitamateCallbackRequest,
    VitamateCitationCallback,
)
from app.client.gemini_client import GeminiClient
from app.core.config import Settings
from app.core.exceptions import VitamateAiGenerateError
from app.service.vitamate_chunk_selector import SelectedVitamateChunk, VitamateChunkSelector
from app.service.vitamate_prompt_builder import VitamatePromptBuilder


class VitamateAnalysisProcessor:
    # Spring에서 받은 분석 작업을 Gemini 분석 결과 callback DTO로 변환합니다.

    def __init__(
        self,
        settings: Settings,
        chunk_selector: VitamateChunkSelector | None = None,
        prompt_builder: VitamatePromptBuilder | None = None,
        gemini_client: GeminiClient | None = None,
    ):
        self._settings = settings
        self._chunk_selector = chunk_selector or VitamateChunkSelector()
        self._prompt_builder = prompt_builder or VitamatePromptBuilder(self._chunk_selector)
        self._gemini_client = gemini_client or GeminiClient(settings)

    def analyze(self, job: VitamateAnalysisJob) -> VitamateCallbackRequest:
        # 동일한 선택 chunk 목록으로 Gemini 입력과 citation 저장값을 함께 만듭니다.
        selected_chunks = self._chunk_selector.select(job)
        if not selected_chunks:
            return self._failed(job, "분석 가능한 문서 chunk가 없습니다.")

        selected_roles = {selected.document.document_role for selected in selected_chunks}
        if not {"REFERENCE", "TARGET"}.issubset(selected_roles):
            return self._failed(job, "기준 문서와 검토 대상 문서의 chunk가 모두 필요합니다.")

        prompt = self._prompt_builder.build_with_selected_chunks(job, selected_chunks)
        citations = self._build_citations(selected_chunks)

        try:
            result = self._gemini_client.generate_text(prompt)
        except VitamateAiGenerateError:
            if self._settings.vitamate_ai_fallback_enabled:
                result = self._build_fallback_result(job, citations)
            else:
                return self._failed(job, "AI 분석 처리 중 오류가 발생했습니다.")

        return VitamateCallbackRequest(
            attemptId=job.attempt_id,
            analysisStatus="COMPLETED",
            result=result,
            citations=citations,
            errorMessage=None,
        )

    def _build_citations(
        self,
        selected_chunks: list[SelectedVitamateChunk],
    ) -> list[VitamateCitationCallback]:
        # 기준과 대상 문서가 모두 근거에 포함되도록 대표 chunk를 먼저 선택합니다.
        citations: list[VitamateCitationCallback] = []
        citation_candidates: list[SelectedVitamateChunk] = []
        for role in ("REFERENCE", "TARGET"):
            representative = next(
                (selected for selected in selected_chunks if selected.document.document_role == role),
                None,
            )
            if representative is not None:
                citation_candidates.append(representative)

        citation_candidates.extend(
            selected for selected in selected_chunks if selected not in citation_candidates
        )

        for selected in citation_candidates[:3]:
            citations.append(
                VitamateCitationCallback(
                    documentChunkId=selected.chunk.document_chunk_id,
                    fileVersionId=selected.document.file_version_id,
                    rankOrder=len(citations) + 1,
                    distanceScore=0.0,
                    excerpt=selected.excerpt[:500],
                )
            )

        return citations

    def _build_fallback_result(
        self,
        job: VitamateAnalysisJob,
        citations: list[VitamateCitationCallback],
    ) -> str:
        # Gemini 쿼터/네트워크 문제 시 local 개발 흐름 검증용 결과를 만듭니다.
        first_excerpt = citations[0].excerpt or "선택된 문서 chunk"

        return (
            "[LOCAL FALLBACK] Gemini 호출 없이 생성한 테스트 분석 결과입니다.\n\n"
            f"검토 유형: {job.review_type}\n"
            f"최종 검토 요청: {job.prompt}\n"
            f"분석 대상 문서 수: {len(job.documents)}개\n"
            f"대표 근거: {first_excerpt}"
        )

    def _failed(self, job: VitamateAnalysisJob, message: str) -> VitamateCallbackRequest:
        # 분석 실패를 Spring callback 형식으로 변환합니다.
        return VitamateCallbackRequest(
            attemptId=job.attempt_id,
            analysisStatus="FAILED",
            result=None,
            citations=[],
            errorMessage=message,
        )
