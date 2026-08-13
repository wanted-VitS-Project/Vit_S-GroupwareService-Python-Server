from app.bidding.client.dto import (
    BidReviewAttachment,
    BidReviewCompanyDocument,
    BidReviewJob,
    BidReviewReferenceFile,
    GeminiBidReviewCitation,
)
from app.bidding.exceptions import BiddingReviewFileError, BiddingReviewGenerateError
from app.bidding.service.bid_review_attachment_stager import StagedAttachment
from app.bidding.service.bid_review_processor import BidReviewProcessor
from app.service.extractor.document_text_extractor import ExtractedTextPage


class _FakeAttachmentStager:
    def __init__(self, results: dict[int, StagedAttachment | Exception]):
        self._results = results

    def stage(self, attachment: BidReviewAttachment) -> StagedAttachment:
        result = self._results[attachment.attachment_id]
        if isinstance(result, Exception):
            raise result
        return result


class _FakeDocumentLoader:
    def __init__(self, results: dict[str, list[ExtractedTextPage] | Exception]):
        self._results = results

    def load(self, url: str, file_name: str) -> list[ExtractedTextPage]:
        result = self._results[url]
        if isinstance(result, Exception):
            raise result
        return result


class _FakeGeminiClient:
    def __init__(self, output=None, error: Exception | None = None):
        self._output = output
        self._error = error

    def generate(self, prompt: str):
        if self._error:
            raise self._error
        return self._output


def _job(
    attachments: list[BidReviewAttachment] | None = None,
    reference_files: list[BidReviewReferenceFile] | None = None,
    company_documents: list[BidReviewCompanyDocument] | None = None,
) -> BidReviewJob:
    return BidReviewJob(
        reviewId=71,
        companyId=10,
        attemptId="4b0f03bb-c04d-4ff0-997b-3ff762cbfe22",
        prompt="보유 인력으로 수행 가능한지 검토해줘.",
        noticeId=1,
        noticeName="스마트시티 통합관제 용역",
        attachments=attachments or [],
        referenceFiles=reference_files or [],
        companyDocuments=company_documents or [],
    )


def _attachment(attachment_id: int = 31) -> BidReviewAttachment:
    return BidReviewAttachment(
        attachmentId=attachment_id,
        fileName="제안요청서.pdf",
        sourceUrl="https://nara.example/31.pdf",
        uploadUrl="https://s3.example/upload?sig=...",
        temporaryStorageKey=f"bidding/reviews/71/attachments/{attachment_id}/key",
    )


def _reference_file() -> BidReviewReferenceFile:
    return BidReviewReferenceFile(
        referenceFileId=501,
        fileName="원가계산_기준.pdf",
        downloadUrl="https://s3.example/501.pdf?sig=...",
    )


def _output_with_valid_citation() -> object:
    class _Output:
        result = "검토 결과입니다."
        citations = [
            GeminiBidReviewCitation(
                documentRole="INTERNAL_REFERENCE",
                referenceFileId=501,
                fileName="원가계산_기준.pdf",
                pageNumber=3,
                excerpt="전기기사 자격 필요",
            )
        ]

    return _Output()


def test_completes_with_ready_documents_and_valid_citations():
    job = _job(attachments=[_attachment()], reference_files=[_reference_file()])
    processor = BidReviewProcessor(
        settings=None,
        attachment_stager=_FakeAttachmentStager(
            {31: StagedAttachment(pages=[ExtractedTextPage(1, "page-1", "본문")], file_size=100, mime_type="application/pdf")}
        ),
        document_loader=_FakeDocumentLoader(
            {"https://s3.example/501.pdf?sig=...": [ExtractedTextPage(3, "page-3", "전기기사 필요")]}
        ),
        gemini_client=_FakeGeminiClient(output=_output_with_valid_citation()),
    )

    result = processor.process(job)

    assert result.review_status == "COMPLETED"
    assert result.result == "검토 결과입니다."
    assert len(result.documents) == 1
    assert result.documents[0].processing_status == "READY"
    assert result.documents[0].temporary_storage_key == "bidding/reviews/71/attachments/31/key"
    assert len(result.citations) == 1
    assert result.citations[0].rank_order == 1
    assert result.citations[0].reference_file_id == 501


def test_drops_citation_referencing_unknown_document():
    job = _job(attachments=[_attachment()])
    unknown_citation_output = type(
        "Output",
        (),
        {
            "result": "검토 결과",
            "citations": [
                GeminiBidReviewCitation(
                    documentRole="INTERNAL_REFERENCE",
                    referenceFileId=999,
                    fileName="존재안함.pdf",
                    excerpt="지어낸 근거",
                )
            ],
        },
    )()

    processor = BidReviewProcessor(
        settings=None,
        attachment_stager=_FakeAttachmentStager(
            {31: StagedAttachment(pages=[], file_size=10, mime_type="application/pdf")}
        ),
        document_loader=_FakeDocumentLoader({}),
        gemini_client=_FakeGeminiClient(output=unknown_citation_output),
    )

    result = processor.process(job)

    assert result.review_status == "COMPLETED"
    assert result.citations == []


def test_fails_when_all_attachments_fail():
    job = _job(attachments=[_attachment()])
    processor = BidReviewProcessor(
        settings=None,
        attachment_stager=_FakeAttachmentStager({31: BiddingReviewFileError("다운로드 실패")}),
        document_loader=_FakeDocumentLoader({}),
        gemini_client=_FakeGeminiClient(),
    )

    result = processor.process(job)

    assert result.review_status == "FAILED"
    assert result.error_code == "DOWNLOAD_FAILED"
    assert result.documents[0].processing_status == "FAILED"


def test_continues_when_only_some_attachments_fail():
    job = _job(attachments=[_attachment(31), _attachment(32)])
    processor = BidReviewProcessor(
        settings=None,
        attachment_stager=_FakeAttachmentStager(
            {
                31: StagedAttachment(pages=[ExtractedTextPage(1, "page-1", "본문")], file_size=100, mime_type="application/pdf"),
                32: BiddingReviewFileError("다운로드 실패"),
            }
        ),
        document_loader=_FakeDocumentLoader({}),
        gemini_client=_FakeGeminiClient(output=type("Output", (), {"result": "결과", "citations": []})()),
    )

    result = processor.process(job)

    assert result.review_status == "COMPLETED"
    statuses = {doc.bid_attachment_id: doc.processing_status for doc in result.documents}
    assert statuses[31] == "READY"
    assert statuses[32] == "FAILED"


def test_fails_retryable_when_gemini_generation_fails():
    job = _job(attachments=[_attachment()])
    processor = BidReviewProcessor(
        settings=None,
        attachment_stager=_FakeAttachmentStager(
            {31: StagedAttachment(pages=[], file_size=10, mime_type="application/pdf")}
        ),
        document_loader=_FakeDocumentLoader({}),
        gemini_client=_FakeGeminiClient(
            error=BiddingReviewGenerateError("temporary", retryable=True)
        ),
    )

    result = processor.process(job)

    assert result.review_status == "FAILED"
    assert result.error_code == "AI_GENERATE_FAILED"
    assert result.retryable is True


def test_skips_reference_document_load_failure_without_failing_job():
    job = _job(attachments=[_attachment()], reference_files=[_reference_file()])
    processor = BidReviewProcessor(
        settings=None,
        attachment_stager=_FakeAttachmentStager(
            {31: StagedAttachment(pages=[], file_size=10, mime_type="application/pdf")}
        ),
        document_loader=_FakeDocumentLoader(
            {"https://s3.example/501.pdf?sig=...": BiddingReviewFileError("추출 실패")}
        ),
        gemini_client=_FakeGeminiClient(output=type("Output", (), {"result": "결과", "citations": []})()),
    )

    result = processor.process(job)

    assert result.review_status == "COMPLETED"
