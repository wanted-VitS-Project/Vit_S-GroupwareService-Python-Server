from app.client.dto import VitamateAnalysisJob
from app.service.vitamate_chunk_selector import (
    MAX_EXCERPT_LENGTH,
    MAX_TOTAL_CHUNKS,
    VitamateChunkSelector,
)


def test_select_skips_blank_excerpt_and_limits_per_document():
    # 빈 excerpt는 제외하고 한 문서에서는 최대 5개 chunk만 선택합니다.
    job = _job(
        documents=[
            _document(
                file_version_id=1,
                chunks=[
                    "",
                    "chunk-1",
                    "chunk-2",
                    "chunk-3",
                    "chunk-4",
                    "chunk-5",
                    "chunk-6",
                ],
            )
        ]
    )

    selected = VitamateChunkSelector().select(job)

    assert [item.excerpt for item in selected] == [
        "chunk-1",
        "chunk-2",
        "chunk-3",
        "chunk-4",
        "chunk-5",
    ]


def test_select_limits_total_chunks():
    # 여러 문서가 들어와도 전체 선택 chunk 수는 15개를 넘지 않습니다.
    job = _job(
        documents=[
            _document(file_version_id=index, chunks=[f"doc-{index}-chunk-{chunk}" for chunk in range(5)])
            for index in range(1, 5)
        ]
    )

    selected = VitamateChunkSelector().select(job)

    assert len(selected) == MAX_TOTAL_CHUNKS
    assert selected[-1].document.file_version_id == 3


def test_select_truncates_long_excerpt():
    # 긴 excerpt는 Gemini 입력 비용을 제한하기 위해 최대 길이로 자릅니다.
    long_excerpt = "가" * (MAX_EXCERPT_LENGTH + 100)
    job = _job(documents=[_document(file_version_id=1, chunks=[long_excerpt])])

    selected = VitamateChunkSelector().select(job)

    assert len(selected) == 1
    assert len(selected[0].excerpt) == MAX_EXCERPT_LENGTH


def _job(documents: list[dict]) -> VitamateAnalysisJob:
    return VitamateAnalysisJob(
        analysisId=1,
        attemptId="attempt-1",
        reviewType="COST_REPORT",
        reviewCategoryCodes=["COST_RESULT"],
        prompt="기준 문서와 비교하여 핵심 요구사항을 검토해줘.",
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
            "fileVersionIds": [document["fileVersionId"] for document in documents],
        },
        documents=documents,
    )


def _document(file_version_id: int, chunks: list[str]) -> dict:
    return {
        "fileVersionId": file_version_id,
        "fileName": f"document-{file_version_id}.pdf",
        "documentRole": "TARGET",
        "chunks": [
            {
                "documentChunkId": file_version_id * 100 + index,
                "chromaId": f"chunk-{file_version_id}-{index}",
                "pageNumber": index + 1,
                "excerpt": excerpt,
            }
            for index, excerpt in enumerate(chunks)
        ],
    }
