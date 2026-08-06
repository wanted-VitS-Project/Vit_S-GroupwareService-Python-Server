from app.client.dto import (
    VitamateAnalysisJob,
    VitamateCallbackRequest,
    VitamateCitationCallback,
)
from app.client.gemini_client import GeminiClient
from app.core.config import Settings
from app.core.exceptions import VitamateAiGenerateError
from app.service.vitamate_prompt_builder import VitamatePromptBuilder


class VitamateAnalysisProcessor:
    # Spring에서 받은 분석 작업을 Gemini 분석 결과로 변환한다.

    def __init__(self, settings: Settings):
        self._settings = settings
        self._prompt_builder = VitamatePromptBuilder()
        self._gemini_client = GeminiClient(settings)

    def analyze(self, job: VitamateAnalysisJob) -> VitamateCallbackRequest:
        # 문서 청크를 Gemini에 전달하고 Spring callback 요청 DTO를 만든다.
        citations = self._build_citations(job)

        if not citations:
            return self._failed(job, "분석 가능한 문서 청크가 없습니다.")

        prompt = self._prompt_builder.build(job)

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

    def _build_citations(self, job: VitamateAnalysisJob) -> list[VitamateCitationCallback]:
        # Gemini 입력에 사용한 청크 중 일부를 분석 근거로 저장한다.
        citations: list[VitamateCitationCallback] = []

        for document in job.documents:
            for chunk in document.chunks:
                if len(citations) >= 3:
                    return citations

                if not chunk.excerpt or not chunk.excerpt.strip():
                    continue

                citations.append(
                    VitamateCitationCallback(
                        documentChunkId=chunk.document_chunk_id,
                        fileVersionId=document.file_version_id,
                        rankOrder=len(citations) + 1,
                        distanceScore=0.0,
                        excerpt=chunk.excerpt[:500],
                    )
                )

        return citations

    def _build_fallback_result(
        self,
        job: VitamateAnalysisJob,
        citations: list[VitamateCitationCallback],
    ) -> str:
        # Gemini 장애/크레딧 부족 시 local 개발 흐름 검증용 결과를 만든다.
        first_excerpt = citations[0].excerpt or "선택한 문서 청크"

        return (
            "[LOCAL FALLBACK] Gemini 호출 없이 생성한 테스트 분석 결과입니다.\n\n"
            f"요청 프롬프트: {job.prompt}\n"
            f"분석 대상 문서 수: {len(job.documents)}개\n"
            f"대표 근거: {first_excerpt}"
        )

    def _failed(self, job: VitamateAnalysisJob, message: str) -> VitamateCallbackRequest:
        # 분석 실패를 Spring callback 형식으로 변환한다.
        return VitamateCallbackRequest(
            attemptId=job.attempt_id,
            analysisStatus="FAILED",
            result=None,
            citations=[],
            errorMessage=message,
        )
