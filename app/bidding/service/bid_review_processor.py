import logging

from app.bidding.client.dto import (
    BidReviewCallbackRequest,
    BidReviewCitationCallback,
    BidReviewDocumentOutcomeCallback,
    BidReviewJob,
    GeminiBidReviewCitation,
)
from app.bidding.client.gemini_review_client import GeminiBidReviewClient
from app.bidding.exceptions import BiddingReviewFileError, BiddingReviewGenerateError
from app.bidding.prompt.bid_review_prompt import LabeledBidReviewDocument, build_bid_review_prompt
from app.bidding.service.bid_review_attachment_stager import BidReviewAttachmentStager
from app.bidding.service.bid_review_document_loader import BidReviewDocumentLoader
from app.core.config import Settings

logger = logging.getLogger(__name__)


class BidReviewProcessor:
    """Spring 작업을 다운로드·추출·Gemini 검토를 거쳐 callback 결과로 변환합니다."""

    def __init__(
        self,
        settings: Settings,
        attachment_stager: BidReviewAttachmentStager | None = None,
        document_loader: BidReviewDocumentLoader | None = None,
        gemini_client: GeminiBidReviewClient | None = None,
    ):
        self._attachment_stager = attachment_stager or BidReviewAttachmentStager()
        self._document_loader = document_loader or BidReviewDocumentLoader()
        self._gemini_client = gemini_client or GeminiBidReviewClient(settings)

    def process(self, job: BidReviewJob) -> BidReviewCallbackRequest:
        document_outcomes: list[BidReviewDocumentOutcomeCallback] = []
        labeled_documents: list[LabeledBidReviewDocument] = []

        for attachment in job.attachments:
            try:
                staged = self._attachment_stager.stage(attachment)
            except BiddingReviewFileError:
                logger.warning(
                    "Bidding review attachment staging failed reviewId=%s attachmentId=%s",
                    job.review_id,
                    attachment.attachment_id,
                )
                document_outcomes.append(
                    BidReviewDocumentOutcomeCallback(
                        bidAttachmentId=attachment.attachment_id,
                        processingStatus="FAILED",
                    )
                )
                continue

            document_outcomes.append(
                BidReviewDocumentOutcomeCallback(
                    bidAttachmentId=attachment.attachment_id,
                    processingStatus="READY",
                    temporaryStorageKey=attachment.temporary_storage_key,
                    fileSize=staged.file_size,
                    mimeType=staged.mime_type,
                )
            )
            labeled_documents.append(
                LabeledBidReviewDocument(
                    document_role="BID_ATTACHMENT",
                    file_name=attachment.file_name,
                    pages=staged.pages,
                    bid_attachment_id=attachment.attachment_id,
                )
            )

        if job.attachments and not any(
            outcome.processing_status == "READY" for outcome in document_outcomes
        ):
            return BidReviewCallbackRequest.failed(
                job.attempt_id,
                "DOWNLOAD_FAILED",
                "선택한 공고 첨부를 하나도 처리할 수 없습니다.",
                documents=document_outcomes,
            )

        for reference_file in job.reference_files:
            self._load_reference_document(
                job.review_id,
                labeled_documents,
                document_role="INTERNAL_REFERENCE",
                document_id=reference_file.reference_file_id,
                file_name=reference_file.file_name,
                url=reference_file.download_url,
                reference_file_id=reference_file.reference_file_id,
            )

        for company_document in job.company_documents:
            self._load_reference_document(
                job.review_id,
                labeled_documents,
                document_role="COMPANY_DOCUMENT_REFERENCE",
                document_id=company_document.company_document_version_id,
                file_name=company_document.file_name,
                url=company_document.download_url,
                company_document_version_id=company_document.company_document_version_id,
            )

        prompt = build_bid_review_prompt(job, labeled_documents)

        try:
            output = self._gemini_client.generate(prompt)
        except BiddingReviewGenerateError as exc:
            return BidReviewCallbackRequest.failed(
                job.attempt_id,
                "AI_GENERATE_FAILED",
                "AI 문서 비교 검토 생성에 실패했습니다.",
                retryable=exc.retryable,
                documents=document_outcomes,
            )

        citations = self._build_valid_citations(output.citations, labeled_documents)

        return BidReviewCallbackRequest.completed(
            job.attempt_id,
            output.result,
            document_outcomes,
            citations,
        )

    def _load_reference_document(
        self,
        review_id: int,
        labeled_documents: list[LabeledBidReviewDocument],
        *,
        document_role: str,
        document_id: int,
        file_name: str,
        url: str,
        reference_file_id: int | None = None,
        company_document_version_id: int | None = None,
    ) -> None:
        # 기준자료·사내문서함은 공고 첨부와 달리 임시 재업로드가 필요 없어 documents[] 항목을 안 만든다 -
        # 이미 생성 시점에 READY로 저장돼 있다(BidReviewDocument 도메인 모델 참고). 추출에 실패하면
        # 이 문서만 근거 후보에서 조용히 빠지고 검토는 계속된다.
        try:
            pages = self._document_loader.load(url, file_name)
        except BiddingReviewFileError:
            logger.warning(
                "Bidding review reference document load failed reviewId=%s documentRole=%s documentId=%s",
                review_id,
                document_role,
                document_id,
            )
            return

        labeled_documents.append(
            LabeledBidReviewDocument(
                document_role=document_role,
                file_name=file_name,
                pages=pages,
                reference_file_id=reference_file_id,
                company_document_version_id=company_document_version_id,
            )
        )

    def _build_valid_citations(
        self,
        citations: list[GeminiBidReviewCitation],
        labeled_documents: list[LabeledBidReviewDocument],
    ) -> list[BidReviewCitationCallback]:
        # Gemini가 지어낸 식별자가 그대로 Spring까지 넘어가지 않게 한 번 더 방어한다
        # (PYTHON_ISSUES.md의 citation 범위 검증 원칙과 동일).
        valid_keys = {self._document_key(document) for document in labeled_documents}

        validated: list[BidReviewCitationCallback] = []
        for citation in citations:
            key = (
                citation.document_role,
                citation.bid_attachment_id,
                citation.reference_file_id,
                citation.company_document_version_id,
            )
            if key not in valid_keys:
                logger.warning("Bidding review citation dropped - unknown document %s", key)
                continue

            validated.append(
                BidReviewCitationCallback(
                    rankOrder=len(validated) + 1,
                    documentRole=citation.document_role,
                    bidAttachmentId=citation.bid_attachment_id,
                    referenceFileId=citation.reference_file_id,
                    companyDocumentVersionId=citation.company_document_version_id,
                    fileName=citation.file_name,
                    pageNumber=citation.page_number,
                    sheetName=citation.sheet_name,
                    excerpt=citation.excerpt,
                )
            )

        return validated

    def _document_key(self, document: LabeledBidReviewDocument) -> tuple:
        return (
            document.document_role,
            document.bid_attachment_id,
            document.reference_file_id,
            document.company_document_version_id,
        )
