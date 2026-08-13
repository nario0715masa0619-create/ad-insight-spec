"""
frontend/streamlit_app.py の認証状態管理を、streamlit.testing.v1.AppTest で
検証するシナリオテスト。

外部依存（実際のFastAPIバックエンド）を避けるため、`st.session_state["api_session"]`
に軽量なフェイクセッション（FakeSession、下記）を事前注入する。streamlit_app.py
冒頭の `if "api_session" not in st.session_state: ...` により、既に
session_state にある場合はそちらがそのまま使われるため、実際のHTTP通信を
一切行わずに認証フローを再現できる。

このテストが直接カバーするのは PR #93 / Issue #95 で修正した以下の回帰:
- モジュールレベル変数の再生成によるAuthorizationヘッダー消失
  （api_session の同一性がrerunをまたいで保持されるか）
- セッション無効化時に再ログイン導線が出るか（Issue #95 fast follow）

実行方法: `cd frontend && PYTHONPATH=. pytest tests/test_auth_state_apptest.py`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")

_LOGIN_RESPONSE_BODY = {
    "session_token": "test-session-token",
    "email": "tester@example.com",
    "is_admin": False,
    "company": {"name": "テスト株式会社", "slug": "test-co"},
    "usage": {"used": 0, "limit": 100, "remaining": 100, "limit_reached": False},
}


class FakeResponse:
    """requests.Response の代わりに使う軽量スタブ。"""

    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or str(json_data)

    def json(self):
        return self._json_data


class FakeSession:
    """
    requests.Session の代わりに st.session_state["api_session"] へ注入する
    フェイク。ログインAPIにだけ既定の成功応答を返し、それ以外は
    `next_response` / `next_get_response` 等で個別のテストが上書きする。
    """

    def __init__(self):
        self.headers = {}
        self.calls = []
        self.next_get_response = None
        self.next_post_response = None
        self.next_delete_response = None

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        if url.endswith("/auth/login"):
            return FakeResponse(200, dict(_LOGIN_RESPONSE_BODY))
        if url.endswith("/auth/logout"):
            return FakeResponse(200, {"success": True})
        if self.next_post_response is not None:
            return self.next_post_response
        return FakeResponse(404, {"error_code": "NOT_FOUND", "error": "not found"})

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if self.next_get_response is not None:
            return self.next_get_response
        return FakeResponse(404, {"error_code": "NOT_FOUND", "error": "not found"})

    def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url))
        if self.next_delete_response is not None:
            return self.next_delete_response
        return FakeResponse(404, {"error_code": "NOT_FOUND", "error": "not found"})


def _login_key(suffix):
    return f"login_{suffix}"


def _new_app_with_fake_session():
    at = AppTest.from_file(APP_PATH)
    fake_session = FakeSession()
    at.session_state["api_session"] = fake_session
    return at, fake_session


def _do_login(at):
    at.text_input(key="login_email_input").input("tester@example.com")
    at.text_input(key="login_password_input").input("correct-password")
    at.button(key="FormSubmitter:login_form-ログイン").click().run(timeout=30)


class TestUnauthenticatedState:
    """未ログイン状態では保護画面に進めないこと。"""

    def test_shows_login_form_only(self):
        at, _ = _new_app_with_fake_session()
        at.run(timeout=30)

        assert not at.exception
        assert len(at.tabs) == 0, "未ログイン時にタブ（保護画面）が描画されてはいけない"
        assert {ti.key for ti in at.text_input} == {"login_email_input", "login_password_input"}

    def test_wrong_password_shows_error_and_stays_on_login_form(self):
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)
        fake_session.next_post_response = None  # login以外は使わない

        # ログインAPI自体を失敗させるため、専用のFakeSessionサブクラス的な
        # 差し替えではなく、next_post_responseを使わずpostを直接上書きする。
        original_post = fake_session.post

        def failing_post(url, **kwargs):
            if url.endswith("/auth/login"):
                return FakeResponse(401, {"error_code": "UNAUTHORIZED", "error": "メールアドレスまたはパスワードが正しくありません。"})
            return original_post(url, **kwargs)

        fake_session.post = failing_post

        at.text_input(key="login_email_input").input("tester@example.com")
        at.text_input(key="login_password_input").input("wrong-password")
        at.button(key="FormSubmitter:login_form-ログイン").click().run(timeout=30)

        assert not at.exception
        assert "auth_token" not in at.session_state
        assert len(at.tabs) == 0
        assert any("正しくありません" in e.value for e in at.error)


class TestSuccessfulLogin:
    """正常ログイン後、必要なstateが保持されること。"""

    def test_login_sets_auth_state_and_shows_protected_tabs(self):
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)

        _do_login(at)

        assert not at.exception
        assert at.session_state["auth_token"] == "test-session-token"
        assert at.session_state["auth_user"]["email"] == "tester@example.com"
        assert len(at.tabs) == 3
        assert [t.label for t in at.tabs] == ["📤 新規分析", "📂 保存済み結果", "🧪 検証"]

    def test_api_session_identity_is_preserved_across_rerun(self):
        """PR #93で修正した回帰の核心: api_session がログイン後の rerun を
        またいで同一オブジェクトのまま保持されること（モジュールレベル変数の
        再生成によるAuthorizationヘッダー消失バグの再発防止）。"""
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)
        _do_login(at)

        assert at.session_state["api_session"] is fake_session

        # ログイン後、何でもよいので別のrerunを発生させる（一覧取得ボタン）。
        fake_session.next_get_response = FakeResponse(200, {"items": [], "total": 0})
        at.button(key="saved_list_fetch_na").click().run(timeout=30)

        assert not at.exception
        assert at.session_state["api_session"] is fake_session
        assert at.session_state["auth_token"] == "test-session-token"

    def test_authorization_header_is_set_after_login(self):
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)
        _do_login(at)

        assert fake_session.headers.get("Authorization") == "Bearer test-session-token"


class TestLogout:
    """ログアウト後、保護状態が解除されること。"""

    def test_logout_clears_auth_state_and_shows_login_form_again(self):
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)
        _do_login(at)
        assert len(at.tabs) == 3

        at.button(key="logout_button").click().run(timeout=30)

        assert not at.exception
        assert "auth_token" not in at.session_state
        assert "auth_user" not in at.session_state
        assert len(at.tabs) == 0
        assert fake_session.headers.get("Authorization") is None


class TestReauthOnSessionInvalidation:
    """認証エラー時に再ログイン導線が表示されること（Issue #95 fast follow）。"""

    @pytest.mark.parametrize(
        "error_code,expected_snippet",
        [
            ("SESSION_EXPIRED", "有効期限が切れました"),
            ("ACCOUNT_DISABLED", "無効化されています"),
            ("COMPANY_DISABLED", "利用は現在停止中"),
        ],
    )
    def test_401_on_list_fetch_triggers_relogin_with_specific_message(self, error_code, expected_snippet):
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)
        _do_login(at)

        fake_session.next_get_response = FakeResponse(
            401, {"success": False, "error_code": error_code, "error": "unused"}
        )
        at.button(key="saved_list_fetch_na").click().run(timeout=30)

        assert not at.exception
        assert "auth_token" not in at.session_state, "セッション無効化時は認証状態がクリアされること"
        assert len(at.tabs) == 0, "再ログイン画面(保護画面ではない)に戻ること"
        assert any(expected_snippet in w.value for w in at.warning), (
            f"再ログイン案内に '{expected_snippet}' を含む文言が表示されること"
        )

    def test_401_on_delete_also_triggers_relogin(self):
        """analyze/list以外の経路(削除)でも同じ再ログイン導線が働くことの確認。
        render_asset_detail() 経由のため、まず新規分析を成功させてから
        削除ボタンを表示させる。"""
        at, fake_session = _new_app_with_fake_session()
        at.run(timeout=30)
        _do_login(at)

        # file_only モードでアップロード無しの分析実行はボタンがdisabledのため、
        # ここでは analysis_result を直接セットして詳細表示だけを再現する
        # （削除ボタンの経路検証が目的で、分析実行フロー自体は別テストの対象外）。
        at.session_state["analysis_result"] = {
            "asset_meta": {"asset_id": "asset_test_0001"},
            "creative_core": {"format": "image_static"},
            "diagnostics": {"qualitative": {"creative_fatigue_risk": "low", "creative_fatigue_basis": "test"}},
            "_metadata": {"input_mode": "file_only"},
            "version": 1,
            "created_at": "2026-08-10T00:00:00Z",
        }
        at.run(timeout=30)
        assert not at.exception

        delete_buttons = [b for b in at.button if b.key and b.key.startswith("analyze_delete_open_")]
        assert delete_buttons, "削除ボタンが見つからない（widget_keyの命名が変わった場合はここを更新）"
        delete_buttons[0].click().run(timeout=30)

        confirm_buttons = [b for b in at.button if b.key and b.key.startswith("analyze_delete_execute_")]
        assert confirm_buttons, "削除確認ボタンが見つからない"

        fake_session.next_delete_response = FakeResponse(
            401, {"success": False, "error_code": "SESSION_EXPIRED", "error": "unused"}
        )
        confirm_buttons[0].click().run(timeout=30)

        assert not at.exception
        assert "auth_token" not in at.session_state
        assert len(at.tabs) == 0
