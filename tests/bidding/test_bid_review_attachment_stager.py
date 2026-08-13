from contextlib import contextmanager

import httpx
import pytest

from app.bidding.client.dto import BidReviewAttachment
from app.bidding.exceptions import BiddingReviewFileError
from app.bidding.service.bid_review_attachment_stager import BidReviewAttachmentStager


class _FakeDownloader:
    def __init__(self, path=None, error: Exception | None = None):
        self._path = path
        self._error = error

    @contextmanager
    def download(self, url: str, file_name: str):
        if self._error:
            raise self._error
        yield self._path


def _attachment(file_name: str = "제안요청서.txt") -> BidReviewAttachment:
    return BidReviewAttachment(
        attachmentId=31,
        fileName=file_name,
        sourceUrl="https://nara.example/31.pdf",
        uploadUrl="https://s3.example/upload?sig=...",
        temporaryStorageKey="bidding/reviews/71/attachments/31/abc",
    )


def test_stage_extracts_and_uploads_successfully(tmp_path, monkeypatch):
    file_path = tmp_path / "downloaded.txt"
    content = "제안요청서 본문 내용입니다.".encode("utf-8")
    file_path.write_bytes(content)

    captured = {}

    def fake_put(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return httpx.Response(200, request=httpx.Request("PUT", url))

    monkeypatch.setattr(httpx, "put", fake_put)

    stager = BidReviewAttachmentStager(downloader=_FakeDownloader(path=file_path))
    result = stager.stage(_attachment())

    assert result.file_size == len(content)
    assert result.mime_type == "text/plain"
    assert len(result.pages) == 1
    assert "제안요청서 본문" in result.pages[0].text
    assert captured["url"] == "https://s3.example/upload?sig=..."
    assert captured["headers"]["Content-Type"] == "application/octet-stream"


def test_stage_wraps_download_failure():
    stager = BidReviewAttachmentStager(
        downloader=_FakeDownloader(error=RuntimeError("connection reset"))
    )

    with pytest.raises(BiddingReviewFileError):
        stager.stage(_attachment())


def test_stage_wraps_upload_rejection(tmp_path, monkeypatch):
    file_path = tmp_path / "downloaded.txt"
    file_path.write_bytes(b"content")

    def fake_put(url, content=None, headers=None, timeout=None):
        return httpx.Response(403, request=httpx.Request("PUT", url))

    monkeypatch.setattr(httpx, "put", fake_put)

    stager = BidReviewAttachmentStager(downloader=_FakeDownloader(path=file_path))

    with pytest.raises(BiddingReviewFileError):
        stager.stage(_attachment())


def test_stage_rejects_missing_extension():
    stager = BidReviewAttachmentStager(downloader=_FakeDownloader())

    with pytest.raises(BiddingReviewFileError):
        stager.stage(_attachment(file_name="확장자없음"))
