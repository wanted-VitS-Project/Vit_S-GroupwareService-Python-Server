import zlib

from app.service.extractor.hwp_text_extractor import HwpTextExtractor, _HWPTAG_PARA_TEXT


def _record(tag_id: int, payload: bytes) -> bytes:
    size = len(payload)
    if size < 0xFFF:
        header = (tag_id & 0x3FF) | ((size & 0xFFF) << 20)
        return header.to_bytes(4, "little") + payload

    header = (tag_id & 0x3FF) | (0xFFF << 20)
    return header.to_bytes(4, "little") + size.to_bytes(4, "little") + payload


def _compress(raw: bytes) -> bytes:
    compressor = zlib.compressobj(level=6, wbits=-15)
    return compressor.compress(raw) + compressor.flush()


def test_supports_hwp_extension_only():
    extractor = HwpTextExtractor()
    assert extractor.supports("hwp") is True
    assert extractor.supports("hwpx") is False


def test_extracts_para_text_records_from_compressed_section():
    text = "제안 마감일은 2026년 8월 30일입니다."
    other_tag_id = 0x10 + 10  # PARA_TEXT가 아닌 임의의 태그 - 결과에 섞이면 안 된다.

    raw = (
        _record(other_tag_id, b"\x00\x00\x00\x00")
        + _record(_HWPTAG_PARA_TEXT, text.encode("utf-16le"))
    )
    compressed = _compress(raw)

    result = HwpTextExtractor()._extract_section_text(compressed)

    assert "제안 마감일" in result


def test_strips_inline_control_characters_from_para_text():
    # 0x0b(표·개체 표시)와 같은 컨트롤 문자가 실제 문장 사이에 섞여도 결과가 안 깨져야 한다.
    payload = "앞".encode("utf-16le") + b"\x0b\x00" + "뒤".encode("utf-16le")
    compressed = _compress(_record(_HWPTAG_PARA_TEXT, payload))

    result = HwpTextExtractor()._extract_section_text(compressed)

    assert "앞" in result
    assert "뒤" in result


def test_returns_empty_string_when_no_para_text_records():
    compressed = _compress(_record(0x10 + 10, b"\x01\x02\x03\x04"))

    result = HwpTextExtractor()._extract_section_text(compressed)

    assert result == ""
