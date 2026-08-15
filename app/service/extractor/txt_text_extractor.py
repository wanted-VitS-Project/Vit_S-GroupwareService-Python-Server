from pathlib import Path

from app.service.extractor.document_text_extractor import ExtractedTextPage


class TxtTextExtractor:
    # 일반 텍스트 파일을 그대로 읽습니다.

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        return extension.lower().lstrip(".") == "txt"

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            return []
        return [ExtractedTextPage(None, None, text)]
