from app.bidding.client.dto import BidReviewJob
from app.bidding.prompt.bid_review_prompt import (
    MAX_CHARS_PER_DOCUMENT,
    LabeledBidReviewDocument,
    build_bid_review_prompt,
)
from app.service.extractor.document_text_extractor import ExtractedTextPage


def _job(qualification_summary: str | None = "전기공학 3명") -> BidReviewJob:
    return BidReviewJob(
        reviewId=71,
        companyId=10,
        attemptId="4b0f03bb-c04d-4ff0-997b-3ff762cbfe22",
        prompt="보유 인력으로 수행 가능한지 검토해줘.",
        noticeId=1,
        noticeName="스마트시티 통합관제 용역",
        qualificationSummary=qualification_summary,
    )


def test_includes_user_prompt_and_qualification_summary():
    prompt = build_bid_review_prompt(_job(), documents=[])

    assert "보유 인력으로 수행 가능한지 검토해줘." in prompt
    assert "전기공학 3명" in prompt


def test_falls_back_when_qualification_summary_missing():
    prompt = build_bid_review_prompt(_job(qualification_summary=None), documents=[])

    assert "제공되지 않음" in prompt


def test_labels_each_document_with_matching_identifier():
    documents = [
        LabeledBidReviewDocument(
            document_role="BID_ATTACHMENT",
            file_name="제안요청서.pdf",
            pages=[ExtractedTextPage(1, "page-1", "제안 마감일은 8월 30일입니다.")],
            bid_attachment_id=31,
        ),
        LabeledBidReviewDocument(
            document_role="INTERNAL_REFERENCE",
            file_name="원가계산_기준.pdf",
            pages=[ExtractedTextPage(3, "page-3", "전기기사 자격 필요")],
            reference_file_id=501,
        ),
        LabeledBidReviewDocument(
            document_role="COMPANY_DOCUMENT_REFERENCE",
            file_name="재무제표.xlsx",
            pages=[ExtractedTextPage(None, "시트1", "매출 10억원")],
            company_document_version_id=9001,
        ),
    ]

    prompt = build_bid_review_prompt(_job(), documents=documents)

    assert "attachmentId=31" in prompt
    assert "제안요청서.pdf" in prompt
    assert "제안 마감일은 8월 30일입니다." in prompt
    assert "referenceFileId=501" in prompt
    assert "companyDocumentVersionId=9001" in prompt


def test_shows_no_extracted_text_marker_for_empty_document():
    documents = [
        LabeledBidReviewDocument(
            document_role="BID_ATTACHMENT",
            file_name="빈파일.pdf",
            pages=[],
            bid_attachment_id=31,
        ),
    ]

    prompt = build_bid_review_prompt(_job(), documents=documents)

    assert "추출된 텍스트 없음" in prompt


def test_truncates_document_text_beyond_per_document_budget():
    long_text = "가" * (MAX_CHARS_PER_DOCUMENT + 500)
    documents = [
        LabeledBidReviewDocument(
            document_role="BID_ATTACHMENT",
            file_name="긴문서.pdf",
            pages=[ExtractedTextPage(1, "page-1", long_text)],
            bid_attachment_id=31,
        ),
    ]

    prompt = build_bid_review_prompt(_job(), documents=documents)

    assert len(prompt) < len(long_text) + 2000
