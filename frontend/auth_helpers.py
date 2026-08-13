"""
frontend/streamlit_app.py の認証状態管理から、Streamlitランタイムに依存しない
純粋なロジックだけを切り出したモジュール。

streamlit_app.py 全体は import するとトップレベルで render_login_gate() /
st.stop() 等が即実行されてしまい、通常のPython importでは安全にテストできない
（AppTestという専用のテストハーネス経由でしか動かせない）。ここに切り出した
関数は Streamlit API を一切呼ばない純粋関数のため、通常のpytestで高速に
ユニットテストできる（frontend/tests/test_auth_helpers.py 参照）。
"""
from typing import Optional


# 再ログインが必要なことを示す401のerror_code一覧（backend/app/api/deps.py::
# get_current_user() が返す4種）と、それぞれのユーザー向け案内文。
# UNAUTHORIZED は「トークン自体が無い」ケース（例: api_session初期化直後の
# 想定外の状態）も含むため、他の3種より汎用的な文言にしている。
REAUTH_MESSAGES = {
    "SESSION_EXPIRED": "セッションの有効期限が切れました。お手数ですが、再度ログインしてください。",
    "ACCOUNT_DISABLED": "このアカウントは現在無効化されています。管理者にお問い合わせください。",
    "COMPANY_DISABLED": "この会社のモニター利用は現在停止中です。管理者にお問い合わせください。",
    "UNAUTHORIZED": "ログインが必要です。再度ログインしてください。",
}


def reauth_message_for_response(response) -> Optional[str]:
    """
    レスポンスが「再ログインが必要」を意味する401かどうかを判定し、該当すれば
    ユーザー向けの案内文を返す（該当しなければNone）。

    `response` は `.status_code` (int) と `.json()` (dict想定) を持つ
    duck-typed オブジェクトであればよい（requests.Response、またはテスト用の
    軽量スタブのどちらでも動く）。

    純粋関数（st.*を一切呼ばない）にしてあるのは、
    - 通常のpytestで高速にユニットテストできるようにするため
    - streamlit_app.py::run_analyze_with_progress() のバックグラウンドスレッド
      内で受け取ったレスポンスに対しても安全に判定できるようにするため
      （実際にst.session_stateへ書き込む側の呼び出しは、必ずメインスレッド側で
      行うこと。streamlit_app.py::handle_reauth_if_needed() のdocstring参照）
    """
    if response is None or getattr(response, "status_code", None) != 401:
        return None
    try:
        body = response.json()
    except Exception:
        return None
    error_code = body.get("error_code") if isinstance(body, dict) else None
    return REAUTH_MESSAGES.get(error_code, REAUTH_MESSAGES["UNAUTHORIZED"])
