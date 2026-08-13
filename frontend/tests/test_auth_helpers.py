"""
auth_helpers.reauth_message_for_response() のユニットテスト。

Streamlitランタイムに依存しない純粋関数のため、AppTestを使わず通常のpytestで
高速に検証できる。実行方法: `cd frontend && PYTHONPATH=. pytest tests/`
（または `pytest frontend/tests` をリポジトリルートから実行する場合は
`PYTHONPATH=frontend` を指定する）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth_helpers import reauth_message_for_response, REAUTH_MESSAGES


class _FakeResponse:
    """requests.Response の代わりに使う軽量スタブ。status_code/.json()のみ持つ。"""

    def __init__(self, status_code, json_data=None, json_raises=False):
        self.status_code = status_code
        self._json_data = json_data
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("invalid json")
        return self._json_data


class TestReauthMessageForResponse:
    def test_none_response_returns_none(self):
        assert reauth_message_for_response(None) is None

    def test_200_response_returns_none(self):
        response = _FakeResponse(200, {"success": True})
        assert reauth_message_for_response(response) is None

    def test_404_response_returns_none(self):
        """401以外（404等）は再ログイン導線の対象外。既存の個別エラー表示に任せる。"""
        response = _FakeResponse(404, {"error_code": "NOT_FOUND"})
        assert reauth_message_for_response(response) is None

    def test_session_expired_returns_matching_message(self):
        response = _FakeResponse(401, {"error_code": "SESSION_EXPIRED"})
        assert reauth_message_for_response(response) == REAUTH_MESSAGES["SESSION_EXPIRED"]

    def test_account_disabled_returns_matching_message(self):
        response = _FakeResponse(401, {"error_code": "ACCOUNT_DISABLED"})
        assert reauth_message_for_response(response) == REAUTH_MESSAGES["ACCOUNT_DISABLED"]

    def test_company_disabled_returns_matching_message(self):
        response = _FakeResponse(401, {"error_code": "COMPANY_DISABLED"})
        assert reauth_message_for_response(response) == REAUTH_MESSAGES["COMPANY_DISABLED"]

    def test_unauthorized_returns_matching_message(self):
        response = _FakeResponse(401, {"error_code": "UNAUTHORIZED"})
        assert reauth_message_for_response(response) == REAUTH_MESSAGES["UNAUTHORIZED"]

    def test_unknown_error_code_falls_back_to_unauthorized_message(self):
        """backendが将来新しい401 error_codeを追加しても、フロントは未知のまま
        クラッシュせず、汎用的な再ログイン案内にフォールバックすること。"""
        response = _FakeResponse(401, {"error_code": "SOME_FUTURE_ERROR_CODE"})
        assert reauth_message_for_response(response) == REAUTH_MESSAGES["UNAUTHORIZED"]

    def test_missing_error_code_falls_back_to_unauthorized_message(self):
        response = _FakeResponse(401, {"error": "no error_code field"})
        assert reauth_message_for_response(response) == REAUTH_MESSAGES["UNAUTHORIZED"]

    def test_non_json_body_returns_none_fail_soft(self):
        """401だがボディがJSONとして読めない場合(プロキシ等が挟まる異常系)、
        例外を投げずNoneを返す(呼び出し側は通常のHTTPエラー表示にフォールバックする)。"""
        response = _FakeResponse(401, json_raises=True)
        assert reauth_message_for_response(response) is None

    def test_all_deps_error_codes_are_covered(self):
        """backend/app/api/deps.py::get_current_user() が実際に返す4種の
        error_codeすべてに、UNAUTHORIZEDへのフォールバックではない専用文言が
        用意されていることの回帰確認。"""
        deps_error_codes = {"UNAUTHORIZED", "SESSION_EXPIRED", "ACCOUNT_DISABLED", "COMPANY_DISABLED"}
        assert deps_error_codes == set(REAUTH_MESSAGES.keys())
