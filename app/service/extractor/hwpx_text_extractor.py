import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.service.extractor.document_text_extractor import ExtractedTextPage

_SECTION_PATH_PATTERN = re.compile(r"^Contents/section(\d+)\.xml$", re.IGNORECASE)


class HwpxTextExtractor:
    # HWPX는 docx·xlsx와 같은 zip+XML 컨테이너다. Contents/section{N}.xml 각각을 한 섹션으로 본다.

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        return extension.lower().lstrip(".") == "hwpx"

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        pages: list[ExtractedTextPage] = []

        with zipfile.ZipFile(file_path) as archive:
            sections = self._sorted_section_names(archive.namelist())
            for index, name in enumerate(sections, start=1):
                text = self._extract_section_text(archive.read(name))
                if text:
                    pages.append(ExtractedTextPage(index, f"section-{index}", text))

        return pages

    def _sorted_section_names(self, names: list[str]) -> list[str]:
        matches = [(name, _SECTION_PATH_PATTERN.match(name)) for name in names]
        matched = [(int(match.group(1)), name) for name, match in matches if match]
        matched.sort(key=lambda pair: pair[0])
        return [name for _, name in matched]

    def _extract_section_text(self, xml_bytes: bytes) -> str:
        root = ElementTree.fromstring(xml_bytes)
        # 태그 구조를 몰라도 되게, 섹션 안의 모든 텍스트 노드를 순서대로 이어붙인다.
        text = "".join(root.itertext())
        return " ".join(text.split()).strip()
