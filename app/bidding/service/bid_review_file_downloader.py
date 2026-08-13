from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import tempfile

import httpx


class BidReviewFileDownloader:
    # 검토 대상 문서(공고 첨부·기준자료·사내문서함)를 URL에서 임시 파일로 내려받는다.
    # 처리가 끝나면 임시 파일을 자동으로 삭제한다.

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    @contextmanager
    def download(self, url: str, file_name: str) -> Iterator[Path]:
        suffix = Path(file_name).suffix
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = Path(temp_file.name)

                with httpx.stream("GET", url, timeout=self._timeout) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        if chunk:
                            temp_file.write(chunk)

            yield temp_path

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
