from contextlib import contextmanager
from pathlib import Path
import tempfile
from collections.abc import Iterator

import httpx

from app.client.dto import VitamateFileIndexSourceResponse


class VitamateFileDownloader:
    # Spring에서 받은 다운로드 URL로 원본 파일을 임시 파일에 저장합니다.

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    @contextmanager
    def download(self, source: VitamateFileIndexSourceResponse) -> Iterator[Path]:
        # 파일 처리가 끝나면 임시 파일을 자동으로 삭제합니다.
        suffix = self._build_suffix(source.extension)
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = Path(temp_file.name)

                with httpx.stream("GET", source.download_url, timeout=self._timeout) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        if chunk:
                            temp_file.write(chunk)

            yield temp_path

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    def _build_suffix(self, extension: str | None) -> str:
        # 임시 파일에도 확장자를 붙여 extractor가 파일 형식을 다루기 쉽게 합니다.
        if not extension:
            return ""

        normalized = extension.strip().lower().lstrip(".")
        return f".{normalized}" if normalized else ""