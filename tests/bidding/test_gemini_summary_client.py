from unittest.mock import Mock

import httpx
import pytest
from google.genai import errors

from app.bidding.client.gemini_summary_client import GeminiBidNoticeSummaryClient
from app.bidding.exceptions import BiddingSummaryGenerateError
from app.core.config import Settings


def test_rate_limit_is_retryable():
    client = _client_raising(errors.ClientError(429, {"message": "quota"}))

    with pytest.raises(BiddingSummaryGenerateError) as captured:
        client.generate("요약해줘")

    assert captured.value.retryable is True


def test_server_error_is_retryable():
    client = _client_raising(errors.ServerError(503, {"message": "unavailable"}))

    with pytest.raises(BiddingSummaryGenerateError) as captured:
        client.generate("요약해줘")

    assert captured.value.retryable is True


def test_timeout_is_retryable():
    client = _client_raising(httpx.ReadTimeout("timed out"))

    with pytest.raises(BiddingSummaryGenerateError) as captured:
        client.generate("요약해줘")

    assert captured.value.retryable is True


def test_connection_error_is_retryable():
    client = _client_raising(httpx.ConnectError("connection failed"))

    with pytest.raises(BiddingSummaryGenerateError) as captured:
        client.generate("요약해줘")

    assert captured.value.retryable is True


@pytest.mark.parametrize("status_code", [400, 401])
def test_invalid_request_or_api_key_is_not_retryable(status_code: int):
    client = _client_raising(errors.ClientError(status_code, {"message": "invalid"}))

    with pytest.raises(BiddingSummaryGenerateError) as captured:
        client.generate("요약해줘")

    assert captured.value.retryable is False


def test_unknown_error_is_not_retryable():
    client = _client_raising(ValueError("invalid response"))

    with pytest.raises(BiddingSummaryGenerateError) as captured:
        client.generate("요약해줘")

    assert captured.value.retryable is False


def _client_raising(exception: Exception) -> GeminiBidNoticeSummaryClient:
    client = GeminiBidNoticeSummaryClient(
        Settings(_env_file=None, gemini_api_key="test-key")
    )
    client._client = Mock()
    client._client.models.generate_content.side_effect = exception
    return client
