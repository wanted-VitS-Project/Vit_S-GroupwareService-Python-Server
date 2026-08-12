from pathlib import Path

from app.service.extractor.csv_text_extractor import CsvTextExtractor
from app.service.extractor.docx_text_extractor import DocxTextExtractor
from app.service.extractor.document_text_extractor import DocumentTextExtractor, ExtractedTextPage
from app.service.extractor.excel_text_extractor import ExcelTextExtractor
from app.service.extractor.pdf_text_extractor import PdfTextExtractor


class ExtractorRegistry:
    # 파일 확장자에 맞는 텍스트 추출기를 찾아 실행합니다.

    def __init__(self, extractors: list[DocumentTextExtractor] | None = None):
        self._extractors = extractors or [
            PdfTextExtractor(),
            ExcelTextExtractor(),
            CsvTextExtractor(),
            DocxTextExtractor(),
        ]

    def extract(
        self,
        file_path: Path,
        extension: str,
        mime_type: str | None = None,
    ) -> list[ExtractedTextPage]:
        for extractor in self._extractors:
            if extractor.supports(extension, mime_type):
                return extractor.extract(file_path)

        raise ValueError(f"Unsupported file extension: {extension}")