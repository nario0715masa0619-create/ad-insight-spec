import os
from unittest import mock
import pytest
from app.config import Settings, get_settings
import app.config as config_module

def test_fixed_env_path():
    """
    複数パスのフォールバックが排除され、
    システム固定の /etc/ad-insight-spec/.env が定義されていることを保証する。
    """
    assert hasattr(config_module, "_ENV_FILE"), "_ENV_FILE が定義されていません"
    assert config_module._ENV_FILE == "/etc/ad-insight-spec/.env", "固定パスが /etc/ad-insight-spec/.env ではありません"

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
