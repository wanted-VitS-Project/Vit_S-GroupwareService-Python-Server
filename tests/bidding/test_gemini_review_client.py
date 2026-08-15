from unittest.mock import Mock

import httpx
import pytest
from google.genai import errors

from app.bidding.client.gemini_review_client import GeminiBidReviewClient
from app.bidding.exceptions import BiddingReviewGenerateError
from app.core.config import Settings


def test_rate_limit_is_retryable():
    client = _client_raising(errors.ClientError(429, {"message": "quota"}))

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is True


def test_server_error_is_retryable():
    client = _client_raising(errors.ServerError(503, {"message": "unavailable"}))

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is True


def test_timeout_is_retryable():
    client = _client_raising(httpx.ReadTimeout("timed out"))

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is True


def test_connection_error_is_retryable():
    client = _client_raising(httpx.ConnectError("connection failed"))

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is True


@pytest.mark.parametrize("status_code", [400, 401])
def test_invalid_request_or_api_key_is_not_retryable(status_code: int):
    client = _client_raising(errors.ClientError(status_code, {"message": "invalid"}))

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is False


def test_unknown_error_is_not_retryable():
    client = _client_raising(ValueError("invalid response"))

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is False


def test_empty_response_text_is_not_retryable():
    client = GeminiBidReviewClient(Settings(_env_file=None, gemini_api_key="test-key"))
    client._client = Mock()
    client._client.models.generate_content.return_value = Mock(text="   ")

    with pytest.raises(BiddingReviewGenerateError) as captured:
        client.generate("검토해줘")

    assert captured.value.retryable is False


def test_parses_result_and_citations_on_success():
    client = GeminiBidReviewClient(Settings(_env_file=None, gemini_api_key="test-key"))
    client._client = Mock()
    client._client.models.generate_content.return_value = Mock(
        text="""
        {
            "result": "검토 요약입니다.",
            "citations": [
                {
                    "documentRole": "INTERNAL_REFERENCE",
                    "referenceFileId": 501,
                    "fileName": "원가계산_기준.pdf",
                    "pageNumber": 3,
                    "excerpt": "전기기사 자격 필요"
                }
            ]
        }
        """
    )

    output = client.generate("검토해줘")

    assert output.result == "검토 요약입니다."
    assert len(output.citations) == 1
    assert output.citations[0].reference_file_id == 501
    assert output.citations[0].excerpt == "전기기사 자격 필요"


def _client_raising(exception: Exception) -> GeminiBidReviewClient:
    client = GeminiBidReviewClient(Settings(_env_file=None, gemini_api_key="test-key"))
    client._client = Mock()
    client._client.models.generate_content.side_effect = exception
    return client
