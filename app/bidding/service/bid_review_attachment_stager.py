from dataclasses import dataclass
from pathlib import Path
import mimetypes

import httpx

from app.bidding.client.dto import BidReviewAttachment
from app.bidding.exceptions import BiddingReviewFileError
from app.bidding.service.bid_review_file_downloader import BidReviewFileDownloader
from app.service.extractor.document_text_extractor import ExtractedTextPage
from app.service.extractor.extractor_registry import ExtractorRegistry

# S3 presigned PUT 서명에 포함된 고정 Content-Type이다(Spring BidReviewJobQueryService 참고).
# 실제 파일 형식과 무관하게 이 값 그대로 PUT해야 한다 - 다르면 403.
_UPLOAD_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class StagedAttachment:
    # 원본에서 내려받아 텍스트 추출·임시 재업로드까지 끝난 공고 첨부 한 건.
    pages: list[ExtractedTextPage]
    file_size: int
    mime_type: str | None


class BidReviewAttachmentStager:
    # 공고 첨부를 원본 URL에서 내려받아 텍스트를 추출하고, Spring이 발급한 presigned URL로
    # 그대로 되올린다. 한 건의 실패가 job 전체를 막지 않도록 BiddingReviewFileError로 감싼다.

    def __init__(
        self,
        downloader: BidReviewFileDownloader | None = None,
        extractor_registry: ExtractorRegistry | None = None,
        timeout: float = 30.0,
    ):
        self._downloader = downloader or BidReviewFileDownloader()
        self._extractor_registry = extractor_registry or ExtractorRegistry()
        self._timeout = timeout

    def stage(self, attachment: BidReviewAttachment) -> StagedAttachment:
        extension = Path(attachment.file_name).suffix.lstrip(".")
        if not extension:
            raise BiddingReviewFileError(
                f"파일 확장자를 확인할 수 없습니다: {attachment.file_name}"
            )

        try:
            with self._downloader.download(
                attachment.source_url, attachment.file_name
            ) as file_path:
                pages = self._extractor_registry.extract(file_path, extension)
                file_size = file_path.stat().st_size
                self._upload(attachment.upload_url, file_path)
        except BiddingReviewFileError:
            raise
        except Exception as exc:
            raise BiddingReviewFileError(
                f"공고 첨부 다운로드·재업로드에 실패했습니다: {attachment.file_name}"
            ) from exc

        mime_type, _ = mimetypes.guess_type(attachment.file_name)
        return StagedAttachment(pages=pages, file_size=file_size, mime_type=mime_type)

    def _upload(self, upload_url: str, file_path: Path) -> None:
        response = httpx.put(
            upload_url,
            content=file_path.read_bytes(),
            headers={"Content-Type": _UPLOAD_CONTENT_TYPE},
            timeout=self._timeout,
        )
        response.raise_for_status()
