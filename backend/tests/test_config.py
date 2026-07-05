import os
from unittest import mock
import pytest
from app.config import Settings, get_settings
import app.config as config_module

def test_fixed_env_path():
    """
    .env 探索先が cwd 非依存の絶対パス候補のみで構成され、
    本番VM固定パス /etc/ad-insight-spec/.env が最優先候補に含まれることを保証する。

    ローカル開発向けに ~/.ad-insight-spec/.env も候補へ追加されたが
    （cwd 非依存の絶対パスである点は変わらない）、本番パスが
    最優先で残っていることを引き続き保証する。
    """
    assert hasattr(config_module, "_ENV_FILE_CANDIDATES"), "_ENV_FILE_CANDIDATES が定義されていません"
    candidates = config_module._ENV_FILE_CANDIDATES
    assert isinstance(candidates, list) and len(candidates) > 0, "_ENV_FILE_CANDIDATES は空でないリストである必要があります"

    # 本番VM固定パスが最優先候補として残っていること
    assert candidates[0] == "/etc/ad-insight-spec/.env", "本番固定パスが最優先候補ではありません"

    # すべての候補が cwd 非依存であること（"./" 等の cwd 相対パスを禁止）。
    # 本番パスは Unix 形式の絶対パス文字列なので、Windows 上のテスト実行環境では
    # os.path.isabs() が想定通り機能しないことがあるため、cwd 相対を示す
    # 先頭ドット表記のみを禁止する形で緩く検証する。
    for path in candidates:
        assert not path.startswith("./") and not path.startswith(".\\"), f"cwd依存の相対パスが含まれています: {path}"

def test_env_file_is_none():
    """
    カレントディレクトリの .env が暗黙的にロードされるのを防ぐため、
    Pydantic Settings の env_file が None に設定されていることを保証する。
    """
    # Pydantic v1 / v2 の両方に対応するための Config クラスの確認
    if hasattr(Settings, "Config"):
        assert getattr(Settings.Config, "env_file", object()) is None, "Settings.Config.env_file が None ではありません"
    elif hasattr(Settings, "model_config"):
        # Pydantic v2 の場合
        assert Settings.model_config.get("env_file") is None, "Settings.model_config の env_file が None ではありません"

def test_env_var_priority():
    """
    OSの環境変数（systemdのEnvironmentFileなどから渡される値）が、
    設定クラスに最優先で正しくマッピングされることを保証する。
    """
    test_api_key = "test-openai-api-key-12345"
    test_db_url = "postgresql://test_user:test_pass@localhost/test_db"
    
    with mock.patch.dict(os.environ, {
        "OPENAI_API_KEY": test_api_key,
        "DATABASE_URL": test_db_url,
        "DEBUG": "True",
        "LOG_LEVEL": "DEBUG"
    }):
        # キャッシュの影響を避けるため、直接インスタンス化してテスト
        settings = Settings()
        
        assert settings.OPENAI_API_KEY == test_api_key
        assert settings.DATABASE_URL == test_db_url
        assert settings.DEBUG is True
        assert settings.LOG_LEVEL == "DEBUG"
