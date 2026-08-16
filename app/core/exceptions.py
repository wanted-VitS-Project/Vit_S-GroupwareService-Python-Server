class SpringVitamateClientError(Exception):
    # Spring 내부 API 호출 중 발생한 공통 예외
    pass


class SpringVitamateAuthError(SpringVitamateClientError):
    # worker token 누락, 불일치, 권한 오류
    pass


class SpringVitamateJobNotFoundError(SpringVitamateClientError):
    # 오래된 메시지이거나 이미 처리되어 조회할 수 없는 작업
    pass


class SpringVitamateTemporaryError(SpringVitamateClientError):
    # 네트워크 오류 또는 Spring 5xx 같은 일시적 실패
    pass


class SpringVitamateBadRequestError(SpringVitamateClientError):
    # Python worker가 잘못된 요청을 보낸 경우
    pass


class VitamateAiGenerateError(Exception):
    """비타메이트 AI 분석 생성 실패를 표현합니다."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable
