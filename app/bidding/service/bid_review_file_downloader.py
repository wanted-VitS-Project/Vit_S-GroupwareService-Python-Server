from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import ipaddress
import socket
import tempfile
from urllib.parse import urlparse

import httpx

from app.bidding.exceptions import BiddingReviewFileError

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 5
# bid.md 다운로드 안전 정책 - 파일당 최대 50MB.
_MAX_RESPONSE_BYTES = 50 * 1024 * 1024


class BidReviewFileDownloader:
    # 검토 대상 문서(공고 첨부·기준자료·사내문서함)를 URL에서 임시 파일로 내려받는다.
    # 처리가 끝나면 임시 파일을 자동으로 삭제한다.
    #
    # ⚠️ 공고 첨부 URL은 외부(나라장터 등) 수집 데이터라 SSRF 위험이 있다 - http/https만 허용하고
    # loopback·private·link-local 대상은 차단한다. redirect도 자동으로 안 따라가고 매 hop을
    # 직접 다시 검증한다(bid.md "다운로드 안전 정책").

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    @contextmanager
    def download(self, url: str, file_name: str) -> Iterator[Path]:
        suffix = Path(file_name).suffix
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = Path(temp_file.name)
                self._fetch(url, temp_file)

            yield temp_path

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    def _fetch(self, url: str, temp_file) -> None:
        current_url = url

        for _ in range(_MAX_REDIRECTS + 1):
            self._validate_url(current_url)

            with httpx.Client(follow_redirects=False, timeout=self._timeout) as client:
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        next_url = response.headers.get("location")
                        if not next_url:
                            raise BiddingReviewFileError(
                                f"리다이렉트 대상이 없습니다: {current_url}"
                            )
                        current_url = httpx.URL(current_url).join(next_url).__str__()
                        continue

                    response.raise_for_status()
                    self._write_bounded(response, temp_file)
                    return

        raise BiddingReviewFileError(f"리다이렉트가 너무 많습니다: {url}")

    def _write_bounded(self, response: httpx.Response, temp_file) -> None:
        written = 0
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            written += len(chunk)
            if written > _MAX_RESPONSE_BYTES:
                raise BiddingReviewFileError("응답 크기가 허용 한도(50MB)를 넘었습니다.")
            temp_file.write(chunk)

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise BiddingReviewFileError(f"허용되지 않는 URL 스킴입니다: {url}")
        if not parsed.hostname:
            raise BiddingReviewFileError(f"URL에 호스트가 없습니다: {url}")
        if not self._is_safe_host(parsed.hostname):
            raise BiddingReviewFileError(f"허용되지 않는 다운로드 대상입니다: {url}")

    def _is_safe_host(self, hostname: str) -> bool:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return False

        if not infos:
            return False

        for _, _, _, _, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False

        return True
