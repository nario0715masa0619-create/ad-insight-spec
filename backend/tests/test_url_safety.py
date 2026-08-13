"""
app.utils.url_safety.is_unsafe_lp_host() のユニットテスト。

specs.py（入力URLの初期検証）とlp_service.py（redirect各hopの再検証、
Issue #97）の両方から共通で使われる判定ロジック本体を、直接テストする。
API層経由のテストはtest_analyze_endpoint.py::TestLpUrlSsrfProtection、
LPServiceのredirect追従ロジックはtest_lp_service_redirect_ssrf.pyを参照
（責務が重複しないよう、ここでは判定関数そのものの入出力のみを検証する）。
"""
import socket
from unittest.mock import patch

import pytest

from app.utils.url_safety import is_unsafe_lp_host


class TestKnownUnsafeHostnames:
    @pytest.mark.parametrize(
        "hostname", ["localhost", "LOCALHOST", "metadata.google.internal", "metadata"]
    )
    def test_blocked_hostnames_are_unsafe(self, hostname):
        assert is_unsafe_lp_host(hostname) is True


class TestUnsafeIpAddresses:
    @pytest.mark.parametrize(
        "hostname",
        [
            "127.0.0.1",  # loopback
            "::1",  # IPv6 loopback
            "169.254.169.254",  # link-local / GCPメタデータ
            "10.0.0.5",  # RFC1918
            "172.16.0.5",  # RFC1918
            "192.168.1.5",  # RFC1918
            "0.0.0.0",  # unspecified
            "::ffff:169.254.169.254",  # IPv4-mapped IPv6 (link-local)
        ],
    )
    def test_unsafe_literal_ips_are_rejected(self, hostname):
        assert is_unsafe_lp_host(hostname) is True


class TestSafePublicIp:
    def test_safe_public_ip_is_not_unsafe(self):
        assert is_unsafe_lp_host("93.184.216.34") is False


class TestUnresolvableHostname:
    def test_unresolvable_hostname_fails_open(self):
        """
        名前解決できないホストは安全側に倒して拒否しない（誤検知よりfetch失敗の
        方が実害が少ないという設計方針）。socket.getaddrinfoをモックして
        実際のネットワーク/DNS依存を排除する。
        """
        with patch("app.utils.url_safety.socket.getaddrinfo", side_effect=socket.gaierror):
            assert is_unsafe_lp_host("this-host-should-not-resolve.invalid") is False
