import zipfile

from app.service.extractor.hwpx_text_extractor import HwpxTextExtractor


def _section_xml(text: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
        "</hp:sec>"
    )
    return xml.encode("utf-8")


def _build_hwpx(path, sections: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in sections.items():
            archive.writestr(name, content)


def test_supports_hwpx_extension_only():
    extractor = HwpxTextExtractor()
    assert extractor.supports("hwpx") is True
    assert extractor.supports("hwp") is False


def test_extracts_text_from_each_section_in_order(tmp_path):
    file_path = tmp_path / "notice.hwpx"
    _build_hwpx(
        file_path,
        {
            "Contents/section1.xml": _section_xml("제 2 조"),
            "Contents/section0.xml": _section_xml("입찰 조건"),
            "version.xml": b"<v/>",
        },
    )

    pages = HwpxTextExtractor().extract(file_path)

    assert len(pages) == 2
    assert "입찰 조건" in pages[0].text
    assert "제 2 조" in pages[1].text
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2


def test_skips_sections_with_no_text(tmp_path):
    file_path = tmp_path / "empty.hwpx"
    _build_hwpx(
        file_path,
        {"Contents/section0.xml": b'<?xml version="1.0"?><hp:sec xmlns:hp="ns"/>'},
    )

    pages = HwpxTextExtractor().extract(file_path)

    assert pages == []
