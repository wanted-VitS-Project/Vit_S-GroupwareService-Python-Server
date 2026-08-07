from app.client.dto import VitamateAnalysisJob
from app.service.vitamate_prompt_builder import VitamatePromptBuilder


def test_build_prompt_separates_reference_and_target_documents():
    # 기준 문서와 검토 대상 문서가 서로 다른 영역에 들어가는지 검증합니다.
    job = VitamateAnalysisJob(
        analysisId=1,
        attemptId="attempt-1",
        reviewType="COST_REPORT",
        reviewCategoryCodes=["COST_RESULT"],
        prompt="기준 문서와 비교하여 금액 불일치를 검토해줘.",
        reviewTemplates=[
            {
                "reviewType": "COST_REPORT",
                "categoryCode": "COST_RESULT",
                "categoryName": "원가계산 결과",
                "promptTemplate": "원가 총액과 항목별 합계가 일치하는지 검토합니다.",
                "templateVersion": "COST_REPORT_V1",
            }
        ],
        searchScope={"projectId": 1, "blockId": 10, "fileVersionIds": [101, 201]},
        documents=[
            {
                "fileVersionId": 101,
                "fileName": "원가검토기준.pdf",
                "documentRole": "REFERENCE",
                "chunks": [
                    {
                        "documentChunkId": 1001,
                        "pageNumber": 2,
                        "excerpt": "일반관리비율은 기준 범위 안에서 적용한다.",
                    }
                ],
            },
            {
                "fileVersionId": 201,
                "fileName": "검토대상.xlsx",
                "documentRole": "TARGET",
                "chunks": [
                    {
                        "documentChunkId": 2001,
                        "pageNumber": 1,
                        "excerpt": "일반관리비율 12%를 적용하였다.",
                    }
                ],
            },
        ],
    )

    prompt = VitamatePromptBuilder().build(job)

    assert "REFERENCE 기준 문서" in prompt
    assert "TARGET 검토 대상 문서" in prompt
    assert "원가검토기준.pdf" in prompt
    assert "검토대상.xlsx" in prompt
    assert "기준 문서와 비교하여 금액 불일치" in prompt
    assert "문서명, 페이지, chunkId" in prompt
