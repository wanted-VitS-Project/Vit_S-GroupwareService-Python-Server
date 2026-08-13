from app.service.extractor.txt_text_extractor import TxtTextExtractor


def test_supports_txt_extension_only():
    extractor = TxtTextExtractor()
    assert extractor.supports("txt") is True
    assert extractor.supports("TXT") is True
    assert extractor.supports("pdf") is False


def test_extracts_file_content_as_single_page(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("검토 참고사항 - 예산 초과 항목 확인", encoding="utf-8")

    pages = TxtTextExtractor().extract(file_path)

    assert len(pages) == 1
    assert "예산 초과" in pages[0].text


def test_returns_empty_list_for_blank_file(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("   \n  ", encoding="utf-8")

    pages = TxtTextExtractor().extract(file_path)

    assert pages == []
