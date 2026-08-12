from app.bidding.client.dto import (
    BidNoticeSummaryCallbackRequest,
    BidNoticeSummaryJob,
)
from app.bidding.client.gemini_summary_client import GeminiBidNoticeSummaryClient
from app.bidding.prompt.bid_notice_summary_prompt import (
    build_bid_notice_summary_prompt,
)
from app.core.config import Settings


class BidNoticeSummaryProcessor:
    """Spring 작업을 Gemini 입력과 callback 결과로 변환합니다."""

    def __init__(
        self,
        settings: Settings,
        gemini_client: GeminiBidNoticeSummaryClient | None = None,
    ):
        self._gemini_client = gemini_client or GeminiBidNoticeSummaryClient(settings)

    def summarize(self, job: BidNoticeSummaryJob) -> BidNoticeSummaryCallbackRequest:
        prompt = build_bid_notice_summary_prompt(job)
        output = self._gemini_client.generate(prompt)
        return BidNoticeSummaryCallbackRequest.completed(job.attempt_id, output)
