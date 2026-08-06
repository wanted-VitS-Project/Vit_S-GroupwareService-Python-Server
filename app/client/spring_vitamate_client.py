import httpx

from app.client.dto import (
    VitamateAnalysisJob,
    VitamateCallbackRequest,
    VitamateCallbackResponse,
    VitamateFileIndexCallbackRequest,
    VitamateFileIndexCallbackResponse,
)
from app.core.config import Settings
from app.core.exceptions import (
    SpringVitamateAuthError,
    SpringVitamateBadRequestError,
    SpringVitamateClientError,
    SpringVitamateJobNotFoundError,
    SpringVitamateTemporaryError,
)


class SpringVitamateClient:
    # Spring Boot 내부 Vitamate API를 호출하는 동기 client입니다.

    def __init__(self, settings: Settings):
        self._base_url = settings.spring_base_url.rstrip("/")
        self._worker_token = settings.vitamate_worker_token
        self._timeout = 10.0

    def get_analysis_job(self, analysis_id: int, attempt_id: str) -> VitamateAnalysisJob:
        # Python worker가 처리할 분석 입력 데이터를 Spring에서 조회합니다.
        url = f"{self._base_url}/internal/v1/vitamate/analyses/{analysis_id}/jobs/{attempt_id}"

        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, headers=self._headers())

        self._raise_for_response(response)
        return VitamateAnalysisJob.model_validate(response.json())

    def send_callback(
        self,
        analysis_id: int,
        callback: VitamateCallbackRequest,
    ) -> VitamateCallbackResponse:
        # AI 분석 결과를 Spring Boot callback API로 전달합니다.
        url = f"{self._base_url}/internal/v1/vitamate/analyses/{analysis_id}/callback"

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url,
                headers=self._headers(),
                json=callback.model_dump(by_alias=True),
            )

        self._raise_for_response(response)
        return VitamateCallbackResponse.model_validate(response.json())

    def send_file_index_callback(
        self,
        file_version_id: int,
        callback: VitamateFileIndexCallbackRequest,
    ) -> VitamateFileIndexCallbackResponse:
        # 파일 인덱싱 상태를 Spring Boot file_index callback API로 전달합니다.
        url = f"{self._base_url}/internal/v1/vitamate/file-indexes/{file_version_id}/callback"

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url,
                headers=self._headers(),
                json=callback.model_dump(by_alias=True),
            )

        self._raise_for_response(response)
        return VitamateFileIndexCallbackResponse.model_validate(response.json())

    def _headers(self) -> dict[str, str]:
        # 내부 API 인증용 worker token 헤더를 구성합니다.
        return {
            "X-Vitamate-Worker-Token": self._worker_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _raise_for_response(self, response: httpx.Response) -> None:
        # Spring 응답 상태를 worker 처리 정책에 맞는 예외로 변환합니다.
        if response.status_code < 400:
            return

        if response.status_code in (401, 403):
            raise SpringVitamateAuthError("Spring worker authentication failed")

        if response.status_code == 400:
            raise SpringVitamateBadRequestError("Spring rejected worker request")

        if response.status_code == 404:
            raise SpringVitamateJobNotFoundError("Spring resource was not found")

        if response.status_code >= 500:
            raise SpringVitamateTemporaryError("Spring internal API temporary failure")

        raise SpringVitamateClientError(
            f"Unexpected Spring response status: {response.status_code}"
        )
