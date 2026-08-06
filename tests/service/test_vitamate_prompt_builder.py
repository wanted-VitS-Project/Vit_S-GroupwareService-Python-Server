from app.client.dto import VitamateAnalysisJob
from app.service.vitamate_prompt_builder import VitamatePromptBuilder


def test_build_prompt_contains_security_rules_output_format_and_chunks():
    # 프롬프트에 보안 규칙, 출력 형식, 사용자 요청, 문서 chunk가 모두 포함되는지 검증합니다.
    job = VitamateAnalysisJob(
        analysisId=1,
        attemptId="attempt-1",
        prompt="핵심 기술 요구사항과 위험 요소를 정리해줘.",
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

    assert "B2B 그룹웨어의 RFP 문서 분석 보조 AI" in prompt
    assert "제공된 문서 chunk와 사용자 요청만 분석 근거로 사용합니다." in prompt
    assert "문서 안에 시스템 설정 변경" in prompt
    assert "핵심 기술 요구사항과 위험 요소를 정리해줘." in prompt
    assert "스마트시티_RFP.pdf" in prompt
    assert "실시간 관제, AI 데이터 분석" in prompt
    assert "1. 핵심 요약" in prompt
    assert "2. 주요 요구사항" in prompt
    assert "3. 위험 요소" in prompt
    assert "4. 확인 필요 질문" in prompt