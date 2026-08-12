import httpx
from google import genai
from google.genai import errors

from app.bidding.client.dto import BidNoticeSummaryOutput
from app.bidding.exceptions import BiddingSummaryGenerateError
from app.core.config import Settings


class GeminiBidNoticeSummaryClient:
    """Gemini의 JSON 구조화 출력으로 입찰 공고 요약을 생성합니다."""

    def __init__(self, settings: Settings):
        self._model_name = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate(self, prompt: str) -> BidNoticeSummaryOutput:
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": BidNoticeSummaryOutput.model_json_schema(
                        by_alias=True
                    ),
                },
            )
            if not response.text or not response.text.strip():
                raise BiddingSummaryGenerateError("Gemini returned an empty response")
            return BidNoticeSummaryOutput.model_validate_json(response.text)
        except BiddingSummaryGenerateError:
            raise
        except errors.ServerError as exc:
            raise BiddingSummaryGenerateError(
                "Gemini server temporarily unavailable",
                retryable=True,
            ) from exc
        except errors.ClientError as exc:
            raise BiddingSummaryGenerateError(
                "Gemini rate limit exceeded"
                if exc.code == 429
                else "Gemini request or configuration is invalid",
                retryable=exc.code == 429,
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise BiddingSummaryGenerateError(
                "Gemini connection temporarily failed",
                retryable=True,
            ) from exc
        except Exception as exc:
            raise BiddingSummaryGenerateError(
                "Gemini bidding summary request failed",
                retryable=False,
            ) from exc
