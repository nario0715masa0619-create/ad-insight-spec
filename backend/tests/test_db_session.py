"""
app/db/session.py の DB接続設定に関するテスト。

DATABASE_URL 環境変数がハードコードで無視される不具合の再発防止。
モジュールレベルの engine 生成はプロセス内で一度しか評価できない（import済み
モジュールがキャッシュされるため、別のDATABASE_URL値での再import検証は
プロセス分離が必要で壊れやすい）ため、方言ごとの connect_args 組み立てロジック
（build_connect_args）を単体でテストする形にしている。
"""
from app.db.session import build_connect_args, SQLALCHEMY_DATABASE_URL, engine
from app.config import get_settings


def test_build_connect_args_sqlite_file():
    assert build_connect_args("sqlite:///./ad_insight.db") == {"check_same_thread": False}


def test_build_connect_args_sqlite_memory():
    assert build_connect_args("sqlite:///:memory:") == {"check_same_thread": False}


def test_build_connect_args_postgresql():
    assert build_connect_args("postgresql://user:password@localhost:5432/ad_insight_spec") == {}


def test_build_connect_args_other_dialect_defaults_to_empty():
    assert build_connect_args("mysql+pymysql://user:password@localhost/db") == {}


def test_module_database_url_sourced_from_settings_not_hardcoded():
    """
    SQLALCHEMY_DATABASE_URL が app.config.Settings.DATABASE_URL（DATABASE_URL環境変数）
    に追従していること。固定文字列に戻す回帰が起きた場合、このテストは環境変数を
    postgres 等に変えて実行しているCI/開発環境では失敗して検知できる。
    """
    assert SQLALCHEMY_DATABASE_URL == get_settings().DATABASE_URL


def test_engine_dialect_matches_configured_url():
    """engineの実際の方言が、設定されたDATABASE_URLのスキームと整合していること"""
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        assert engine.dialect.name == "sqlite"
    elif SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
        assert engine.dialect.name == "postgresql"
