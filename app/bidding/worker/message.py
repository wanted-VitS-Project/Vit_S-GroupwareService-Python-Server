from pydantic import BaseModel, Field


class BidNoticeSummaryJobMessage(BaseModel):
    """Redis Stream에서 전달되는 입찰 공고 요약 작업 식별자입니다."""

    summary_id: int = Field(gt=0, alias="summaryId")
    company_id: int = Field(gt=0, alias="companyId")
    attempt_id: str = Field(min_length=1, alias="attemptId")
    retry_count: int = Field(default=0, ge=0, alias="retryCount")

    model_config = {"populate_by_name": True}


class BidReviewJobMessage(BaseModel):
    """Redis Stream에서 전달되는 입찰 문서 검토 작업 식별자입니다."""

    review_id: int = Field(gt=0, alias="reviewId")
    company_id: int = Field(gt=0, alias="companyId")
    attempt_id: str = Field(min_length=1, alias="attemptId")
    retry_count: int = Field(default=0, ge=0, alias="retryCount")

    model_config = {"populate_by_name": True}
