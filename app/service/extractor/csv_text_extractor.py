import csv
from pathlib import Path

from app.service.extractor.document_text_extractor import ExtractedTextPage


class CsvTextExtractor:
    # CSV 파일을 행 단위 텍스트로 변환합니다.

    def supports(self, extension: str, mime_type: str | None = None) -> bool:
        return extension.lower().lstrip(".") == "csv"

    def extract(self, file_path: Path) -> list[ExtractedTextPage]:
        rows: list[str] = []

        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            for row in reader:
                values = [value.strip() for value in row if value and value.strip()]
                if values:
                    rows.append(" | ".join(values))

        text = "\n".join(rows).strip()
        return [ExtractedTextPage(1, file_path.name, text)] if text else []