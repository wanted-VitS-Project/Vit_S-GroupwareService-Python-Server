from types import SimpleNamespace

from app.client.dto import VitamateAnalysisJob
from app.service.vitamate_analysis_processor import VitamateAnalysisProcessor


def test_analyze_uses_same_selected_chunks_for_prompt_and_citations():
    # Gemini에 보낸 chunk와 Spring에 저장할 citation chunk가 같은 선택 규칙을 따르는지 검증합니다.
    gemini_client = FakeGeminiClient()
    processor = VitamateAnalysisProcessor(
        settings=SimpleNamespace(vitamate_ai_fallback_enabled=False),
        gemini_client=gemini_client,
    )
    job = _job(
        chunks=[
            "chunk-1",
            "chunk-2",
            "chunk-3",
            "chunk-4",
            "chunk-5",
            "chunk-6",
        ]
    )

    callback = processor.analyze(job)

    assert callback.analysis_status == "COMPLETED"
    assert "COST_RESULT" in gemini_client.last_prompt
    assert "원가 총액과 항목별 합계" in gemini_client.last_prompt
    assert "chunk-1" in gemini_client.last_prompt
    assert "chunk-5" in gemini_client.last_prompt
    assert "chunk-6" not in gemini_client.last_prompt
    assert [citation.document_chunk_id for citation in callback.citations] == [100, 101, 102]
    assert [citation.excerpt for citation in callback.citations] == ["chunk-1", "chunk-2", "chunk-3"]


def test_analyze_returns_failed_when_no_selectable_chunks():
    # 분석 가능한 chunk가 없으면 Gemini를 호출하지 않고 FAILED callback을 만듭니다.
    gemini_client = FakeGeminiClient()
    processor = VitamateAnalysisProcessor(
        settings=SimpleNamespace(vitamate_ai_fallback_enabled=False),
        gemini_client=gemini_client,
    )

    callback = processor.analyze(_job(chunks=["", "   ", None]))

    assert callback.analysis_status == "FAILED"
    assert callback.error_message == "분석 가능한 문서 chunk가 없습니다."
    assert gemini_client.last_prompt is None


class FakeGeminiClient:
    # 테스트에서 실제 Gemini 호출 없이 전달된 프롬프트만 기록합니다.

    def __init__(self):
        self.last_prompt: str | None = None

    def generate_text(self, prompt: str) -> str:
        self.last_prompt = prompt
        return "분석 결과"


def _job(chunks: list[str | None]) -> VitamateAnalysisJob:
    return VitamateAnalysisJob(
        analysisId=1,
        attemptId="attempt-1",
        reviewType="COST_REPORT",
        reviewCategoryCodes=["COST_RESULT"],
        additionalInstruction="핵심 요구사항을 정리해줘.",
        reviewTemplates=[
            {
                "reviewType": "COST_REPORT",
                "categoryCode": "COST_RESULT",
                "categoryName": "I. 원가계산 결과",
                "promptTemplate": "원가 총액과 항목별 합계가 일치하는지 검토합니다.",
                "templateVersion": "COST_REPORT_V1",
            }
        ],
        searchScope={
            "projectId": 1,
            "blockId": 900001,
            "fileVersionIds": [900001],
        },
        documents=[
            {
                "fileVersionId": 900001,
                "fileName": "스마트시티_RFP.pdf",
                "chunks": [
                    {
                        "documentChunkId": 100 + index,
                        "chromaId": f"chunk-{index}",
                        "pageNumber": index + 1,
                        "excerpt": excerpt,
                    }
                    for index, excerpt in enumerate(chunks)
                ],
            }
        ],
    )
