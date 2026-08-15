import re
import zlib
from pathlib import Path

import olefile

from app.service.extractor.document_text_extractor import ExtractedTextPage

# HWP5 레코드 태그 ID (hwp5 스펙: HWPTAG_BEGIN=0x10, PARA_TEXT=BEGIN+51).
_HWPTAG_PARA_TEXT = 0x10 + 51

# 문단 안에 섞여 들어오는 확장 컨트롤 문자(표·그림 등 개체 자리 표시)를 제거한다.
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f]")

_SECTION_PATTERN = re.compile(r"^Section(\d+)$", re.IGNORECASE)


class HwpTextExtractor:
    # 구버전 HWP(OLE 복합 문서)의 본문 텍스트를 레코드 단위로 직접 파싱한다.
    # 암호화된 문서 등 파싱에 실패하는 경우는 이 문서만 추출 실패로 처리한다(호출자가 처리).

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        return extension.lower().lstrip(".") == "hwp"

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        pages: list[ExtractedTextPage] = []

        with olefile.OleFileIO(str(file_path)) as ole:
            for index, section_number in enumerate(self._sorted_section_numbers(ole), start=1):
                raw = ole.openstream(["BodyText", f"Section{section_number}"]).read()
                text = self._extract_section_text(raw)
                if text:
                    pages.append(ExtractedTextPage(index, f"section-{index}", text))

        return pages

    def _sorted_section_numbers(self, ole: "olefile.OleFileIO") -> list[int]:
        numbers = []
        for entry in ole.listdir():
            if len(entry) == 2 and entry[0] == "BodyText":
                match = _SECTION_PATTERN.match(entry[1])
                if match:
                    numbers.append(int(match.group(1)))
        return sorted(numbers)

    def _extract_section_text(self, raw: bytes) -> str:
        # HWP5 BodyText 스트림은 raw deflate(zlib 헤더 없음)로 압축돼 있다.
        decompressed = zlib.decompressobj(-15).decompress(raw)

        fragments: list[str] = []
        offset = 0
        length = len(decompressed)

        while offset + 4 <= length:
            header = int.from_bytes(decompressed[offset : offset + 4], "little")
            tag_id = header & 0x3FF
            size = (header >> 20) & 0xFFF
            offset += 4

            if size == 0xFFF:
                if offset + 4 > length:
                    break
                size = int.from_bytes(decompressed[offset : offset + 4], "little")
                offset += 4

            payload = decompressed[offset : offset + size]
            offset += size

            if tag_id == _HWPTAG_PARA_TEXT:
                text = payload.decode("utf-16le", errors="ignore")
                text = _CONTROL_CHAR_PATTERN.sub(" ", text)
                if text.strip():
                    fragments.append(text.strip())

        return " ".join(fragments)
