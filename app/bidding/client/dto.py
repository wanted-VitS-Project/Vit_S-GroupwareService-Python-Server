from datetime import datetime
from decimal import Decimal
from typing import Literal

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


# ── 입찰 문서 비교 검토 (bid review) ──────────────────────────────────────
# 요약(BidNoticeSummary)과는 별개 기능이다. Spring이 job 하나로 필요한 걸 전부 내려주는
# 구조는 같지만, 검토는 실제 파일(첨부·기준자료·사내문서함)을 다운로드해서 비교해야 한다.


class BidReviewAttachment(BaseModel):
    """검토 대상 공고 첨부 - 나라장터 등 원본 URL만 있고 아직 우리 S3엔 없다.

    uploadUrl/temporaryStorageKey는 원본을 내려받아 우리 임시 저장소에 되올리기 위한 것이다.
    PUT 시 Content-Type을 반드시 application/octet-stream으로 보내야 한다(서명에 포함됨).
    """

    attachment_id: int = Field(alias="attachmentId")
    file_name: str = Field(alias="fileName")
    source_url: str = Field(alias="sourceUrl")
    upload_url: str = Field(alias="uploadUrl")
    temporary_storage_key: str = Field(alias="temporaryStorageKey")

    model_config = {"populate_by_name": True}


class BidReviewReferenceFile(BaseModel):
    """검토 근거로 선택한 사내 기준자료(bid_reference_file) - 단명 다운로드 URL."""

    reference_file_id: int = Field(alias="referenceFileId")
    file_name: str = Field(alias="fileName")
    download_url: str = Field(alias="downloadUrl")

    model_config = {"populate_by_name": True}


class BidReviewCompanyDocument(BaseModel):
    """검토 근거로 선택한 사내 문서함(company_document_version) - 단명 다운로드 URL."""

    company_document_version_id: int = Field(alias="companyDocumentVersionId")
    file_name: str = Field(alias="fileName")
    download_url: str = Field(alias="downloadUrl")

    model_config = {"populate_by_name": True}


class BidReviewJob(BaseModel):
    """Python worker가 조회하는 현재 입찰 문서 검토 작업입니다."""

    review_id: int = Field(gt=0, alias="reviewId")
    company_id: int = Field(gt=0, alias="companyId")
    attempt_id: str = Field(min_length=1, alias="attemptId")
    prompt: str = Field(min_length=1)
    notice_id: int = Field(gt=0, alias="noticeId")
    notice_name: str = Field(alias="noticeName")
    attachments: list[BidReviewAttachment] = Field(default_factory=list)
    reference_files: list[BidReviewReferenceFile] = Field(
        default_factory=list,
        alias="referenceFiles",
    )
    company_documents: list[BidReviewCompanyDocument] = Field(
        default_factory=list,
        alias="companyDocuments",
    )
    qualification_summary: str | None = Field(default=None, alias="qualificationSummary")

    model_config = {"populate_by_name": True}


class BidReviewDocumentOutcomeCallback(BaseModel):
    """공고 첨부 한 건의 다운로드·임시저장 처리 결과입니다. 공고 첨부에만 쓴다."""

    bid_attachment_id: int = Field(alias="bidAttachmentId")
    processing_status: str = Field(alias="processingStatus")
    temporary_storage_key: str | None = Field(default=None, alias="temporaryStorageKey")
    file_size: int | None = Field(default=None, alias="fileSize")
    mime_type: str | None = Field(default=None, alias="mimeType")

    model_config = {"populate_by_name": True}


class BidReviewCitationCallback(BaseModel):
    """검토 결과 근거 한 건입니다. documentRole에 맞는 식별자만 채운다."""

    rank_order: int = Field(alias="rankOrder")
    document_role: str = Field(alias="documentRole")
    bid_attachment_id: int | None = Field(default=None, alias="bidAttachmentId")
    reference_file_id: int | None = Field(default=None, alias="referenceFileId")
    company_document_version_id: int | None = Field(
        default=None,
        alias="companyDocumentVersionId",
    )
    file_name: str = Field(alias="fileName")
    page_number: int | None = Field(default=None, alias="pageNumber")
    sheet_name: str | None = Field(default=None, alias="sheetName")
    excerpt: str = Field(alias="excerpt")

    model_config = {"populate_by_name": True}


class BidReviewCallbackRequest(BaseModel):
    """입찰 문서 검토 결과를 Spring callback API로 전달하는 요청입니다."""

    attempt_id: str = Field(alias="attemptId")
    review_status: str = Field(alias="reviewStatus")
    result: str | None = None
    error_code: str | None = Field(default=None, alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")
    retryable: bool = False
    documents: list[BidReviewDocumentOutcomeCallback] = Field(default_factory=list)
    citations: list[BidReviewCitationCallback] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @classmethod
    def processing(
        cls,
        attempt_id: str,
        documents: list[BidReviewDocumentOutcomeCallback],
    ) -> "BidReviewCallbackRequest":
        return cls(
            attemptId=attempt_id,
            reviewStatus="PROCESSING",
            documents=documents,
        )

    @classmethod
    def completed(
        cls,
        attempt_id: str,
        result: str,
        documents: list[BidReviewDocumentOutcomeCallback],
        citations: list[BidReviewCitationCallback],
    ) -> "BidReviewCallbackRequest":
        return cls(
            attemptId=attempt_id,
            reviewStatus="COMPLETED",
            result=result,
            documents=documents,
            citations=citations,
        )

    @classmethod
    def failed(
        cls,
        attempt_id: str,
        error_code: str,
        error_message: str,
        *,
        retryable: bool = False,
        documents: list[BidReviewDocumentOutcomeCallback] | None = None,
    ) -> "BidReviewCallbackRequest":
        return cls(
            attemptId=attempt_id,
            reviewStatus="FAILED",
            errorCode=error_code,
            errorMessage=error_message,
            retryable=retryable,
            documents=documents or [],
        )


class BidReviewCallbackResponse(BaseModel):
    """Spring callback API의 멱등 처리 결과입니다."""

    accepted: bool
    review_id: int = Field(alias="reviewId")
    review_status: str = Field(alias="reviewStatus")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class GeminiBidReviewCitation(BaseModel):
    """Gemini가 생성하는 근거 한 건입니다. rankOrder는 여기 없다 - Python이 목록 순서로 매긴다.

    documentRole을 Literal로 못박아 JSON 스키마에 enum 제약을 건다 - 실측 결과 이렇게 안 하면
    Gemini가 "공고 첨부" 같은 한글 라벨을 자유롭게 지어내 citation이 통째로 드롭됐다(2026-08-13 확인).
    """

    document_role: Literal[
        "BID_ATTACHMENT",
        "INTERNAL_REFERENCE",
        "COMPANY_DOCUMENT_REFERENCE",
    ] = Field(alias="documentRole")
    bid_attachment_id: int | None = Field(default=None, alias="bidAttachmentId")
    reference_file_id: int | None = Field(default=None, alias="referenceFileId")
    company_document_version_id: int | None = Field(
        default=None,
        alias="companyDocumentVersionId",
    )
    file_name: str = Field(alias="fileName")
    page_number: int | None = Field(default=None, alias="pageNumber")
    sheet_name: str | None = Field(default=None, alias="sheetName")
    excerpt: str = Field(min_length=1, alias="excerpt")

    model_config = {"populate_by_name": True}


class BidReviewGeminiOutput(BaseModel):
    """Gemini가 생성해야 하는 검토 결과와 근거 목록입니다."""

    result: str = Field(min_length=1)
    citations: list[GeminiBidReviewCitation] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
