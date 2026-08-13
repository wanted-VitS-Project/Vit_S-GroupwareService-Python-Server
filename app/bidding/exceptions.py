class SpringBiddingClientError(Exception):
    """Spring 입찰 내부 API 호출 실패입니다."""


class SpringBiddingAuthError(SpringBiddingClientError):
    """입찰 worker 토큰 인증 실패입니다."""


class SpringBiddingBadRequestError(SpringBiddingClientError):
    """Spring이 입찰 worker 요청을 잘못된 요청으로 거절했습니다."""


class SpringBiddingJobNotFoundError(SpringBiddingClientError):
    """입찰 요약 작업이 없거나 현재 시도와 일치하지 않습니다."""


class SpringBiddingTemporaryError(SpringBiddingClientError):
    """네트워크 또는 Spring 5xx와 같은 일시적인 실패입니다."""


class BiddingSummaryGenerateError(Exception):
    """입찰 공고 AI 요약 생성 실패입니다."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class BiddingReviewGenerateError(Exception):
    """입찰 문서 비교 검토 AI 생성 실패입니다."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class BiddingReviewFileError(Exception):
    """검토 대상 문서 한 건의 다운로드 또는 텍스트 추출 실패입니다. 이 문서만 실패로 처리하고
    나머지 문서로 검토를 계속하기 위해 job 전체를 중단시키는 예외와 분리한다."""

    def __init__(self, message: str):
        super().__init__(message)
