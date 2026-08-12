import httpx

from app.bidding.client.dto import (
    BidNoticeSummaryCallbackRequest,
    BidNoticeSummaryCallbackResponse,
    BidNoticeSummaryJob,
)
from app.bidding.exceptions import (
    SpringBiddingAuthError,
    SpringBiddingBadRequestError,
    SpringBiddingClientError,
    SpringBiddingJobNotFoundError,
    SpringBiddingTemporaryError,
)
from app.core.config import Settings


class SpringBiddingClient:
    """Spring Boot 입찰 요약 내부 API를 호출합니다."""

    def __init__(self, settings: Settings):
        self._base_url = settings.spring_base_url.rstrip("/")
        self._worker_token = settings.bidding_worker_token
        self._timeout = 10.0

    def get_summary_job(self, summary_id: int, attempt_id: str) -> BidNoticeSummaryJob:
        url = (
            f"{self._base_url}/internal/v1/bidding/summaries/"
            f"{summary_id}/jobs/{attempt_id}"
        )
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                response = client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise SpringBiddingTemporaryError("Spring bidding API connection failed") from exc

        self._raise_for_response(response)
        return BidNoticeSummaryJob.model_validate(response.json())

    def send_summary_callback(
        self,
        summary_id: int,
        callback: BidNoticeSummaryCallbackRequest,
    ) -> BidNoticeSummaryCallbackResponse:
        url = f"{self._base_url}/internal/v1/bidding/summaries/{summary_id}/callback"
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                response = client.post(
                    url,
                    headers=self._headers(),
                    json=callback.model_dump(by_alias=True),
                )
        except httpx.HTTPError as exc:
            raise SpringBiddingTemporaryError("Spring bidding API connection failed") from exc

        self._raise_for_response(response)
        return BidNoticeSummaryCallbackResponse.model_validate(response.json())

    def _headers(self) -> dict[str, str]:
        return {
            "X-Bidding-Worker-Token": self._worker_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code in (401, 403):
            raise SpringBiddingAuthError("Spring bidding worker authentication failed")
        if response.status_code == 400:
            raise SpringBiddingBadRequestError("Spring rejected bidding worker request")
        if response.status_code == 404:
            raise SpringBiddingJobNotFoundError("Spring bidding summary job was not found")
        if response.status_code >= 500:
            raise SpringBiddingTemporaryError("Spring bidding API temporary failure")
        raise SpringBiddingClientError(
            f"Unexpected Spring bidding response status: {response.status_code}"
        )
