from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BidNoticeAttachment(BaseModel):
    """Spring이 전달한 입찰 공고 첨부 메타데이터입니다."""

    attachment_order: int | None = Field(default=None, alias="attachmentOrder")
    file_name: str | None = Field(default=None, alias="fileName")
    source_url: str | None = Field(default=None, alias="sourceUrl")

    model_config = {"populate_by_name": True}


class BidNoticeSnapshot(BaseModel):
    """요약 요청 시점의 입찰 공고 구조화 스냅샷입니다."""

    notice_id: int = Field(alias="noticeId")
    notice_name: str = Field(alias="noticeName")
    notice_type: str | None = Field(default=None, alias="noticeType")
    notice_agency: str | None = Field(default=None, alias="noticeAgency")
    demand_agency: str | None = Field(default=None, alias="demandAgency")
    base_amount: Decimal | None = Field(default=None, alias="baseAmount")
    estimated_amount: Decimal | None = Field(default=None, alias="estimatedAmount")
    announced_at: datetime | None = Field(default=None, alias="announcedAt")
    bid_start_at: datetime | None = Field(default=None, alias="bidStartAt")
    bid_deadline_at: datetime | None = Field(default=None, alias="bidDeadlineAt")
    opening_at: datetime | None = Field(default=None, alias="openingAt")
    participation_qualification_text: str | None = Field(
        default=None,
        alias="participationQualificationText",
    )
    region_limit_text: str | None = Field(default=None, alias="regionLimitText")
    business_limit_text: str | None = Field(default=None, alias="businessLimitText")
    contract_method: str | None = Field(default=None, alias="contractMethod")
    evaluation_method: str | None = Field(default=None, alias="evaluationMethod")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    attachments: list[BidNoticeAttachment] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class BidNoticeSummaryJob(BaseModel):
    """Spring 내부 API에서 조회한 현재 입찰 요약 작업입니다."""

    summary_id: int = Field(gt=0, alias="summaryId")
    company_id: int = Field(gt=0, alias="companyId")
    attempt_id: str = Field(min_length=1, alias="attemptId")
    prompt: str = Field(min_length=1)
    notice: BidNoticeSnapshot

    model_config = {"populate_by_name": True}


class BidNoticeSummaryOutput(BaseModel):
    """Gemini가 생성해야 하는 구조화 요약 결과입니다."""

    overview_summary: str = Field(min_length=1, alias="overviewSummary")
    amount_summary: str | None = Field(default=None, alias="amountSummary")
    schedule_summary: str | None = Field(default=None, alias="scheduleSummary")
    qualification_summary: str | None = Field(
        default=None,
        alias="qualificationSummary",
    )
    task_summary: str | None = Field(default=None, alias="taskSummary")
    risk_summary: str | None = Field(default=None, alias="riskSummary")

    model_config = {"populate_by_name": True}


class BidNoticeSummaryCallbackRequest(BaseModel):
    """입찰 요약 결과를 Spring callback API로 전달하는 요청입니다."""

    attempt_id: str = Field(alias="attemptId")
    summary_status: str = Field(alias="summaryStatus")
    overview_summary: str | None = Field(default=None, alias="overviewSummary")
    amount_summary: str | None = Field(default=None, alias="amountSummary")
    schedule_summary: str | None = Field(default=None, alias="scheduleSummary")
    qualification_summary: str | None = Field(
        default=None,
        alias="qualificationSummary",
    )
    task_summary: str | None = Field(default=None, alias="taskSummary")
    risk_summary: str | None = Field(default=None, alias="riskSummary")
    error_message: str | None = Field(default=None, alias="errorMessage")
    retryable: bool = False

    model_config = {"populate_by_name": True}

    @classmethod
    def completed(
        cls,
        attempt_id: str,
        output: BidNoticeSummaryOutput,
    ) -> "BidNoticeSummaryCallbackRequest":
        return cls(
            attemptId=attempt_id,
            summaryStatus="COMPLETED",
            overviewSummary=output.overview_summary,
            amountSummary=output.amount_summary,
            scheduleSummary=output.schedule_summary,
            qualificationSummary=output.qualification_summary,
            taskSummary=output.task_summary,
            riskSummary=output.risk_summary,
            errorMessage=None,
            retryable=False,
        )

    @classmethod
    def failed(
        cls,
        attempt_id: str,
        error_message: str,
        retryable: bool = False,
    ) -> "BidNoticeSummaryCallbackRequest":
        return cls(
            attemptId=attempt_id,
            summaryStatus="FAILED",
            errorMessage=error_message,
            retryable=retryable,
        )


class BidNoticeSummaryCallbackResponse(BaseModel):
    """Spring callback API의 멱등 처리 결과입니다."""

    accepted: bool
    summary_id: int = Field(alias="summaryId")
    summary_status: str = Field(alias="summaryStatus")
    reason: str | None = None

    model_config = {"populate_by_name": True}
