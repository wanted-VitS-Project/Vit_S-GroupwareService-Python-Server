from pathlib import Path

from pypdf import PdfReader

from app.service.extractor.document_text_extractor import ExtractedTextPage


class PdfTextExtractor:
    # PDF 페이지별 텍스트를 추출합니다.

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        return extension.lower().lstrip(".") == "pdf"

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        reader = PdfReader(str(file_path))
        pages: list[ExtractedTextPage] = []

        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(ExtractedTextPage(index, f"page-{index}", text))

        return pages