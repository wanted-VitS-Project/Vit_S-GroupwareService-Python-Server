from unittest.mock import Mock

from app.bidding.client.dto import BidNoticeSummaryJob, BidNoticeSummaryOutput
from app.bidding.service.bid_notice_summary_processor import BidNoticeSummaryProcessor
from app.core.config import Settings


def test_processor_returns_completed_callback_with_structured_output():
    gemini_client = Mock()
    gemini_client.generate.return_value = BidNoticeSummaryOutput(
        overviewSummary="스마트시티 통합관제 플랫폼 구축 용역입니다.",
        amountSummary="추정금액은 3억 3천만 원입니다.",
        scheduleSummary="마감일은 2026년 8월 26일입니다.",
        qualificationSummary="유사 사업 실적이 필요합니다.",
        taskSummary="통합관제 플랫폼 구축이 주요 과업입니다.",
        riskSummary="제출 일정과 실적 증빙을 확인해야 합니다.",
    )
    processor = BidNoticeSummaryProcessor(
        Settings(_env_file=None, gemini_api_key="test-key"),
        gemini_client=gemini_client,
    )

    callback = processor.summarize(_job())

    assert callback.summary_status == "COMPLETED"
    assert callback.attempt_id == "attempt-1"
    assert callback.overview_summary == "스마트시티 통합관제 플랫폼 구축 용역입니다."
    assert callback.error_message is None
    generated_prompt = gemini_client.generate.call_args.args[0]
    assert "금액, 일정, 참가 자격과 위험을 정리해줘." in generated_prompt
    assert "스마트시티 통합관제 플랫폼 구축 용역" in generated_prompt


def _job() -> BidNoticeSummaryJob:
    return BidNoticeSummaryJob(
        summaryId=1,
        companyId=10,
        attemptId="attempt-1",
        prompt="금액, 일정, 참가 자격과 위험을 정리해줘.",
        notice={
            "noticeId": 317,
            "noticeName": "스마트시티 통합관제 플랫폼 구축 용역",
            "noticeType": "SERVICE",
            "noticeAgency": "서울특별시",
            "estimatedAmount": 330000000,
            "attachments": [],
        },
    )
