"""
LPService._fetch_url_revalidating_redirects() のテスト（Issue #97）。

PR #93で追加した`lp_url`のSSRF対策（backend/app/utils/url_safety.py::
is_unsafe_lp_host()）は、入力URLそのものに対する検証に留まり、
requestsのallow_redirects=True（既定）が内部で自動追従するredirect先までは
検証していなかった。本テストは、redirectを1hopずつ追跡して都度ホストを
再検証する新しい実装（LPService._fetch_url_revalidating_redirects()）の
挙動を検証する。

すべて`requests.get`をモックし、実際のネットワークI/O・DNS解決を発生させない
（危険/安全ホストはリテラルIPアドレス、またはis_unsafe_lp_host()が明示的に
拒否するホスト名のみを使う）。API層（specs.py）の初期入力検証テストは
test_analyze_endpoint.py::TestLpUrlSsrfProtection を参照（責務が重複しない
よう、ここではLPService内部のredirect追従ロジックのみを検証する）。
"""
import socket
from unittest.mock import patch

import pytest

from app.services.base_service import ProcessingError
from app.services.lp_service import LPService, LPUnsafeRedirectError

SAFE_URL_1 = "https://93.184.216.34/lp"
SAFE_URL_2 = "https://93.184.216.35/lp-canonical"
LOOPBACK_URL = "http://127.0.0.1/steal"
LOCALHOST_URL = "http://localhost/steal"
METADATA_URL = "http://169.254.169.254/computeMetadata/v1/"
PRIVATE_IP_URL = "http://10.0.0.5/steal"
IPV6_LOOPBACK_URL = "http://[::1]/steal"
UNRESOLVABLE_URL = "https://this-host-should-not-resolve.invalid/lp"


class _FakeResponse:
    """requests.Response の代わりに使う軽量スタブ。"""

    def __init__(self, status_code, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _redirect(location, status_code=302):
    return _FakeResponse(status_code, headers={"Location": location})


def _ok(text="<html><h1>Safe LP</h1></html>"):
    return _FakeResponse(200, text=text)


def _mock_get_from_table(url_to_response: dict):
    """URL -> FakeResponse の対応表から、都度ルックアップして返すモックを作る。
    未知のURLでの呼び出しはテストのバグとして即座に失敗させる。"""

    def _fake_get(url, timeout=None, allow_redirects=None):
        if url not in url_to_response:
            raise AssertionError(f"想定外のURLへのリクエスト: {url}")
        return url_to_response[url]

    return _fake_get


class TestSafeUrlIsFetchedDirectly:
    def test_safe_url_without_redirect_is_fetched(self):
        """1. 安全なURLをそのままfetchできる"""
        service = LPService()
        with patch(
            "app.services.lp_service.requests.get",
            side_effect=_mock_get_from_table({SAFE_URL_1: _ok("<html><h1>OK</h1></html>")}),
        ):
            html = service._fetch_html(SAFE_URL_1)
        assert "OK" in html


class TestSafeRedirectIsAllowed:
    def test_safe_external_to_safe_external_redirect_is_followed(self):
        """2. 安全な外部URL → 安全な外部URL への redirect は許可される"""
        service = LPService()
        table = {
            SAFE_URL_1: _redirect(SAFE_URL_2),
            SAFE_URL_2: _ok("<html><h1>Canonical</h1></html>"),
        }
        with patch("app.services.lp_service.requests.get", side_effect=_mock_get_from_table(table)):
            html = service._fetch_html(SAFE_URL_1)
        assert "Canonical" in html

    def test_relative_redirect_is_resolved_against_current_url(self):
        """8. 相対redirectが正しく解決される（http→httpsのスキーム正規化も許容）"""
        service = LPService()
        table = {
            "http://93.184.216.34/old-path": _redirect("/new-path", status_code=301),
            "http://93.184.216.34/new-path": _ok("<html><h1>Moved</h1></html>"),
        }
        with patch("app.services.lp_service.requests.get", side_effect=_mock_get_from_table(table)):
            html = service._fetch_html("http://93.184.216.34/old-path")
        assert "Moved" in html


class TestUnsafeRedirectIsRejected:
    @pytest.mark.parametrize(
        "unsafe_url",
        [
            LOOPBACK_URL,
            LOCALHOST_URL,
            METADATA_URL,
            PRIVATE_IP_URL,
            IPV6_LOOPBACK_URL,
        ],
        ids=["loopback_ip", "localhost_hostname", "metadata_link_local", "rfc1918_private", "ipv6_loopback"],
    )
    def test_redirect_to_unsafe_host_is_rejected(self, unsafe_url):
        """3〜6. 安全な外部URL → 内部アドレス/metadataエンドポイントへのredirectは拒否される"""
        service = LPService()
        table = {SAFE_URL_1: _redirect(unsafe_url)}
        with patch("app.services.lp_service.requests.get", side_effect=_mock_get_from_table(table)):
            with pytest.raises(LPUnsafeRedirectError):
                service._fetch_html(SAFE_URL_1)

    def test_unsafe_redirect_appearing_mid_chain_is_rejected(self):
        """安全な外部URLを複数hop経由した後、途中のhopで危険URLが出るケースも拒否される"""
        service = LPService()
        table = {
            SAFE_URL_1: _redirect(SAFE_URL_2),
            SAFE_URL_2: _redirect(METADATA_URL),
        }
        with patch("app.services.lp_service.requests.get", side_effect=_mock_get_from_table(table)):
            with pytest.raises(LPUnsafeRedirectError):
                service._fetch_html(SAFE_URL_1)

    def test_unsafe_initial_url_is_rejected_without_any_request(self):
        """初期URL自体が危険な場合、requests.get自体が一度も呼ばれずに拒否される
        （LPService単体でも、specs.py側の事前検証を経ずに呼ばれた場合の防御になっている
        ことの確認）"""
        service = LPService()
        with patch("app.services.lp_service.requests.get") as mock_get:
            with pytest.raises(LPUnsafeRedirectError):
                service._fetch_html(LOOPBACK_URL)
            mock_get.assert_not_called()


class TestRedirectLimits:
    def test_exceeding_max_redirects_fails_safely(self):
        """7. redirect回数上限超過時に安全に失敗する（無限redirectで固まらない）"""
        service = LPService()
        # MAX_REDIRECTS+1 を超える回数、安全なホスト同士でredirectし続けるチェーンを作る
        table = {}
        for i in range(service.MAX_REDIRECTS + 3):
            table[f"https://93.184.216.34/hop{i}"] = _redirect(f"https://93.184.216.34/hop{i + 1}")

        with patch("app.services.lp_service.requests.get", side_effect=_mock_get_from_table(table)):
            with pytest.raises(ProcessingError):
                service._fetch_html("https://93.184.216.34/hop0")

    def test_redirect_without_location_header_fails_safely(self):
        """Locationヘッダーを欠いた不正な3xxレスポンスでも例外で安全に失敗する"""
        service = LPService()
        table = {SAFE_URL_1: _FakeResponse(302, headers={})}
        with patch("app.services.lp_service.requests.get", side_effect=_mock_get_from_table(table)):
            with pytest.raises(ProcessingError):
                service._fetch_html(SAFE_URL_1)


class TestUnresolvableHostname:
    def test_unresolvable_hostname_is_not_blocked_by_redirect_check(self):
        """
        名前解決できないホストは、redirect再検証の時点でも拒否しない
        （app.utils.url_safety.is_unsafe_lp_hostの設計方針を踏襲。誤検知より
        fetch失敗の方が実害が少ないため）。実際のfetch自体はrequests.get
        （モック）が呼ばれ、そのモックが返す結果がそのまま使われることを確認する。
        """
        service = LPService()
        with patch("app.services.lp_service.requests.get", return_value=_ok("<html><h1>Unresolvable but allowed through</h1></html>")):
            with patch("app.utils.url_safety.socket.getaddrinfo", side_effect=socket.gaierror):
                html = service._fetch_html(UNRESOLVABLE_URL)
        assert "Unresolvable but allowed through" in html
