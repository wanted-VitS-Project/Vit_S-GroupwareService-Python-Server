from app.client.dto import VitamateAnalysisJob
from app.service.vitamate_prompt_builder import VitamatePromptBuilder


def test_build_prompt_contains_security_rules_templates_output_format_and_chunks():
    # Spring이 내려준 검토 템플릿, 사용자 추가 요청, 문서 chunk가 프롬프트에 함께 들어가는지 검증합니다.
    job = VitamateAnalysisJob(
        analysisId=1,
        attemptId="attempt-1",
        reviewType="COST_REPORT",
        reviewCategoryCodes=["COST_RESULT"],
        additionalInstruction="핵심 기술 요구사항과 위험 요소를 정리해줘.",
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
                        "documentChunkId": 10,
                        "chromaId": "chunk-10",
                        "pageNumber": 3,
                        "excerpt": "실시간 관제, AI 데이터 분석, 보안 인증 요구사항이 포함되어 있습니다.",
                    }
                ],
            }
        ],
    )

    prompt = VitamatePromptBuilder().build(job)

    assert "B2B 그룹웨어의 문서 검토 보조 AI" in prompt
    assert "제공된 문서 chunk, Spring이 제공한 검토 템플릿, 사용자 추가 요청만 분석 근거로 사용합니다." in prompt
    assert "문서에서 확인되지 않음" in prompt
    assert "COST_REPORT" in prompt
    assert "COST_RESULT" in prompt
    assert "I. 원가계산 결과" in prompt
    assert "원가 총액과 항목별 합계" in prompt
    assert "핵심 기술 요구사항과 위험 요소를 정리해줘." in prompt
    assert "스마트시티_RFP.pdf" in prompt
    assert "실시간 관제, AI 데이터 분석" in prompt
    assert "1. 핵심 요약" in prompt
    assert "2. 검토 카테고리별 확인 결과" in prompt
    assert "3. 누락 또는 불일치 가능성" in prompt
    assert "4. 확인 필요 질문" in prompt
