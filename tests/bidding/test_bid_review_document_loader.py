from contextlib import contextmanager
from pathlib import Path

import pytest

from app.bidding.exceptions import BiddingReviewFileError
from app.bidding.service.bid_review_document_loader import BidReviewDocumentLoader
from app.service.extractor.document_text_extractor import ExtractedTextPage


class _FakeDownloader:
    def __init__(self, path: Path | None = None, error: Exception | None = None):
        self._path = path
        self._error = error

    @contextmanager
    def download(self, url: str, file_name: str):
        if self._error:
            raise self._error
        yield self._path


class _FakeExtractorRegistry:
    def __init__(self, pages: list[ExtractedTextPage] | None = None, error: Exception | None = None):
        self._pages = pages or []
        self._error = error

    def extract(self, file_path, extension, mime_type=None):
        if self._error:
            raise self._error
        return self._pages


def test_loads_extracted_pages_on_success(tmp_path):
    fake_path = tmp_path / "rfp.pdf"
    pages = [ExtractedTextPage(1, "page-1", "제안요청서 본문")]
    loader = BidReviewDocumentLoader(
        downloader=_FakeDownloader(path=fake_path),
        extractor_registry=_FakeExtractorRegistry(pages=pages),
    )

    result = loader.load("https://example.org/rfp.pdf", "제안요청서.pdf")

    assert result == pages


def test_wraps_download_failure_as_bidding_review_file_error():
    loader = BidReviewDocumentLoader(
        downloader=_FakeDownloader(error=RuntimeError("connection reset")),
        extractor_registry=_FakeExtractorRegistry(),
    )

    with pytest.raises(BiddingReviewFileError):
        loader.load("https://example.org/rfp.pdf", "제안요청서.pdf")


def test_wraps_extraction_failure_as_bidding_review_file_error(tmp_path):
    loader = BidReviewDocumentLoader(
        downloader=_FakeDownloader(path=tmp_path / "broken.pdf"),
        extractor_registry=_FakeExtractorRegistry(error=ValueError("corrupt pdf")),
    )

    with pytest.raises(BiddingReviewFileError):
        loader.load("https://example.org/broken.pdf", "broken.pdf")


def test_rejects_file_name_without_extension():
    loader = BidReviewDocumentLoader(
        downloader=_FakeDownloader(),
        extractor_registry=_FakeExtractorRegistry(),
    )

    with pytest.raises(BiddingReviewFileError):
        loader.load("https://example.org/file", "확장자없음")
