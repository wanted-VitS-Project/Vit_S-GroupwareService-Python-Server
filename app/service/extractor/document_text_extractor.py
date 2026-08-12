from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ExtractedTextPage:
    # 추출된 문서 텍스트의 한 구간입니다.
    page_number: int | None
    section_title: str | None
    text: str


class DocumentTextExtractor(Protocol):
    # 파일 확장자별 텍스트 추출기가 지켜야 하는 공통 계약입니다.

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        ...

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        ...