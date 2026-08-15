import socket

import httpx
import pytest

from app.bidding.exceptions import BiddingReviewFileError
from app.bidding.service.bid_review_file_downloader import BidReviewFileDownloader

_PUBLIC_IP = "8.8.8.8"  # 실제로 전역 공개된 주소 - is_private/is_reserved 어디에도 안 걸린다.


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.is_redirect = 300 <= status_code < 400
        self._chunks = chunks or [b"content"]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def iter_bytes(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeClient:
    def __init__(self, responses_by_url):
        self._responses_by_url = responses_by_url

    def stream(self, method, url):
        return self._responses_by_url[url]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _stub_public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port: [(socket.AF_INET, None, None, None, (_PUBLIC_IP, 0))],
    )


def test_rejects_disallowed_scheme(tmp_path):
    downloader = BidReviewFileDownloader()

    with pytest.raises(BiddingReviewFileError):
        with downloader.download("ftp://example.org/file.pdf", "file.pdf") as _:
            pass


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "169.254.1.1"])
def test_rejects_loopback_private_and_link_local_hosts(host, monkeypatch):
    def fake_getaddrinfo(hostname, port):
        ip = "127.0.0.1" if hostname == "localhost" else hostname
        return [(socket.AF_INET, None, None, None, (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    downloader = BidReviewFileDownloader()

    with pytest.raises(BiddingReviewFileError):
        with downloader.download(f"http://{host}/file.pdf", "file.pdf") as _:
            pass


def test_rejects_unresolvable_host(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port: (_ for _ in ()).throw(socket.gaierror("no such host")),
    )
    downloader = BidReviewFileDownloader()

    with pytest.raises(BiddingReviewFileError):
        with downloader.download("http://no-such-host.example/file.pdf", "file.pdf") as _:
            pass


def test_downloads_successfully_from_public_host(monkeypatch, tmp_path):
    _stub_public_dns(monkeypatch)
    url = "https://example.org/rfp.pdf"
    fake_client = _FakeClient({url: _FakeResponse(chunks=[b"hello ", b"world"])})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    downloader = BidReviewFileDownloader()
    with downloader.download(url, "rfp.pdf") as path:
        content = path.read_bytes()

    assert content == b"hello world"


def test_follows_redirect_to_another_safe_public_host(monkeypatch):
    _stub_public_dns(monkeypatch)
    first_url = "https://example.org/redirect"
    final_url = "https://cdn.example.org/rfp.pdf"
    fake_client = _FakeClient(
        {
            first_url: _FakeResponse(status_code=302, headers={"location": final_url}),
            final_url: _FakeResponse(chunks=[b"final content"]),
        }
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    downloader = BidReviewFileDownloader()
    with downloader.download(first_url, "rfp.pdf") as path:
        content = path.read_bytes()

    assert content == b"final content"


def test_rejects_redirect_to_unsafe_host(monkeypatch):
    def fake_getaddrinfo(hostname, port):
        if hostname == "internal.example":
            return [(socket.AF_INET, None, None, None, ("10.0.0.5", 0))]
        return [(socket.AF_INET, None, None, None, (_PUBLIC_IP, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    first_url = "https://example.org/redirect"
    unsafe_url = "https://internal.example/secret"
    fake_client = _FakeClient(
        {first_url: _FakeResponse(status_code=302, headers={"location": unsafe_url})}
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    downloader = BidReviewFileDownloader()
    with pytest.raises(BiddingReviewFileError):
        with downloader.download(first_url, "rfp.pdf") as _:
            pass


def test_rejects_too_many_redirects(monkeypatch):
    _stub_public_dns(monkeypatch)
    urls = [f"https://example.org/hop{i}" for i in range(8)]
    responses = {
        urls[i]: _FakeResponse(status_code=302, headers={"location": urls[i + 1]})
        for i in range(len(urls) - 1)
    }
    responses[urls[-1]] = _FakeResponse(status_code=302, headers={"location": "https://example.org/final"})
    fake_client = _FakeClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    downloader = BidReviewFileDownloader()
    with pytest.raises(BiddingReviewFileError):
        with downloader.download(urls[0], "rfp.pdf") as _:
            pass


def test_rejects_response_larger_than_50mb(monkeypatch):
    _stub_public_dns(monkeypatch)
    url = "https://example.org/huge.pdf"
    oversized_chunk = b"0" * (51 * 1024 * 1024)
    fake_client = _FakeClient({url: _FakeResponse(chunks=[oversized_chunk])})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: fake_client)

    downloader = BidReviewFileDownloader()
    with pytest.raises(BiddingReviewFileError):
        with downloader.download(url, "huge.pdf") as _:
            pass
