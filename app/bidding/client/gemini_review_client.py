import httpx
from google import genai
from google.genai import errors

from app.bidding.client.dto import BidReviewGeminiOutput
from app.bidding.exceptions import BiddingReviewGenerateError
from app.core.config import Settings


class GeminiBidReviewClient:
    """Gemini의 JSON 구조화 출력으로 입찰 문서 비교 검토 결과를 생성합니다."""

    def __init__(self, settings: Settings):
        self._model_name = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate(self, prompt: str) -> BidReviewGeminiOutput:
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": BidReviewGeminiOutput.model_json_schema(
                        by_alias=True
                    ),
                },
            )
            if not response.text or not response.text.strip():
                raise BiddingReviewGenerateError("Gemini returned an empty response")
            return BidReviewGeminiOutput.model_validate_json(response.text)
        except BiddingReviewGenerateError:
            raise
        except errors.ServerError as exc:
            raise BiddingReviewGenerateError(
                "Gemini server temporarily unavailable",
                retryable=True,
            ) from exc
        except errors.ClientError as exc:
            raise BiddingReviewGenerateError(
                "Gemini rate limit exceeded"
                if exc.code == 429
                else "Gemini request or configuration is invalid",
                retryable=exc.code == 429,
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise BiddingReviewGenerateError(
                "Gemini connection temporarily failed",
                retryable=True,
            ) from exc
        except Exception as exc:
            raise BiddingReviewGenerateError(
                "Gemini bidding review request failed",
                retryable=False,
            ) from exc
