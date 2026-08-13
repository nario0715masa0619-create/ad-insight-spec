"""
外部からの入力URLがサーバー側フェッチ(SSRF)の踏み台にならないかを判定する
共通ユーティリティ。

背景: `lp_url`（`backend/app/api/routes/specs.py::analyze()`）はサーバー側
（`LPService`）から任意のURLへGETリクエストを行う経路であり、認証済みユーザーが
指定したホストがloopback/link-local（クラウドメタデータエンドポイント含む）/
RFC1918プライベートIP等の内部アドレスに解決される場合、SSRFの踏み台になりうる。

このロジックは元々API層（specs.py）に閉じていたが、redirect追従時の再検証
（`LPService`側、Issue #97）でも同じ判定が必要になったため、共通モジュールへ
切り出した。API層（入力URLの初期検証）・service層（redirect各hopの再検証）の
両方から同じ関数を呼ぶことで、判定ロジックの二重実装を避けている。
"""
import ipaddress
import socket

# ホスト名として拒否する既知の内部/メタデータ向け名称
# （IPアドレスへの解決結果は is_unsafe_lp_host() 内で別途判定する）
BLOCKED_LP_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata"}


def is_unsafe_lp_host(hostname: str) -> bool:
    """
    サーバー側フェッチ対象のホストが、loopback/link-local（クラウドメタデータ
    エンドポイント含む）/RFC1918プライベートIP等の内部向けアドレスに解決されない
    かを確認する。

    認証済みユーザーが指定した任意のURLをサーバー側からGETするため、本番環境
    （GCP）上でメタデータエンドポイント（169.254.169.254等）や内部ネットワークへ
    到達できてしまうSSRFを防ぐための最低限のチェック。
    """
    if hostname.lower() in BLOCKED_LP_HOSTNAMES:
        return True
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # 名前解決できないホストは後続のフェッチでもどのみち失敗するため、
        # ここでは安全側に倒して拒否しない（誤検知よりfetch失敗の方が実害が少ない）
        return False
    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_private
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False
