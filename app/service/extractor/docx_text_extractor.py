from pathlib import Path

from docx import Document

from app.service.extractor.document_text_extractor import ExtractedTextPage


class DocxTextExtractor:
    # Word 문서의 문단 텍스트를 추출합니다.

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        return extension.lower().lstrip(".") == "docx"

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        document = Document(str(file_path))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        text = "\n".join(paragraphs).strip()

        return [ExtractedTextPage(1, file_path.name, text)] if text else []