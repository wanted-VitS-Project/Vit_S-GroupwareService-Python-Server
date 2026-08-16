from unittest.mock import Mock

import httpx
import pytest
from google.genai import errors

from app.client.gemini_embedding_client import GeminiEmbeddingClient
from app.core.config import Settings
from app.core.exceptions import VitamateAiGenerateError


def test_rate_limit_is_retryable():
    client = _client_raising(errors.ClientError(429, {"message": "quota"}))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("문서 내용")

    assert captured.value.retryable is True


def test_server_error_is_retryable():
    client = _client_raising(errors.ServerError(503, {"message": "unavailable"}))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("문서 내용")

    assert captured.value.retryable is True


def test_timeout_is_retryable():
    client = _client_raising(httpx.ReadTimeout("timed out"))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("문서 내용")

    assert captured.value.retryable is True


def test_connection_error_is_retryable():
    client = _client_raising(httpx.ConnectError("connection failed"))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("문서 내용")

    assert captured.value.retryable is True


@pytest.mark.parametrize("status_code", [400, 401])
def test_invalid_request_or_api_key_is_not_retryable(status_code: int):
    client = _client_raising(errors.ClientError(status_code, {"message": "invalid"}))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("문서 내용")

    assert captured.value.retryable is False


def test_unknown_error_is_not_retryable():
    client = _client_raising(ValueError("invalid response"))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("문서 내용")

    assert captured.value.retryable is False


def test_empty_text_is_not_retryable():
    client = GeminiEmbeddingClient(Settings(_env_file=None, gemini_api_key="test-key"))

    with pytest.raises(VitamateAiGenerateError) as captured:
        client.embed_text("   ")

    assert captured.value.retryable is False


def _client_raising(exception: Exception) -> GeminiEmbeddingClient:
    client = GeminiEmbeddingClient(Settings(_env_file=None, gemini_api_key="test-key"))
    client._client = Mock()
    client._client.models.embed_content.side_effect = exception
    return client
