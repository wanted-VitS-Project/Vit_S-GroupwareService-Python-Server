from pathlib import Path

from app.bidding.exceptions import BiddingReviewFileError
from app.bidding.service.bid_review_file_downloader import BidReviewFileDownloader
from app.service.extractor.document_text_extractor import ExtractedTextPage
from app.service.extractor.extractor_registry import ExtractorRegistry


class BidReviewDocumentLoader:
    # 다운로드와 텍스트 추출을 묶어, 문서 한 건의 실패가 나머지 문서에 영향을 주지 않게 한다.

    def __init__(
        self,
        downloader: BidReviewFileDownloader | None = None,
        extractor_registry: ExtractorRegistry | None = None,
    ):
        self._downloader = downloader or BidReviewFileDownloader()
        self._extractor_registry = extractor_registry or ExtractorRegistry()

    def load(self, url: str, file_name: str) -> list[ExtractedTextPage]:
        extension = Path(file_name).suffix.lstrip(".")
        if not extension:
            raise BiddingReviewFileError(f"파일 확장자를 확인할 수 없습니다: {file_name}")

        try:
            with self._downloader.download(url, file_name) as file_path:
                return self._extractor_registry.extract(file_path, extension)
        except BiddingReviewFileError:
            raise
        except Exception as exc:
            raise BiddingReviewFileError(
                f"문서 다운로드 또는 텍스트 추출에 실패했습니다: {file_name}"
            ) from exc
