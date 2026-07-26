from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Dict, Any

from app.config import get_settings

# DB接続先は app.config.Settings.DATABASE_URL を正本とする（DATABASE_URL 環境変数、
# 未設定時はローカル開発用に sqlite:///./ad_insight.db にフォールバック）。
# ここでハードコードしない: 以前はこのモジュールが独自に "sqlite:///./ad_insight.db" を
# 固定していたため、.env や環境変数で DATABASE_URL=postgresql://... を指定しても
# 実際には無視されSQLiteに接続し続けるという不具合があった。
SQLALCHEMY_DATABASE_URL = get_settings().DATABASE_URL


def build_connect_args(database_url: str) -> Dict[str, Any]:
    """
    DB方言ごとの connect_args を組み立てる。

    SQLite は複数スレッドからの同一コネクション共有に check_same_thread=False が
    必要だが、Postgres 等の他方言にこの引数を渡すと create_engine() がエラーに
    なるため、方言ごとに出し分ける。
    """
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


_connect_args = build_connect_args(SQLALCHEMY_DATABASE_URL)

# エンジン生成
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=_connect_args,
    echo=False  # 本番は False
)

# セッションファクトリー
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# FastAPI 依存注入用
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI のエンドポイント内で使用する DB セッション取得関数
    
    使用例:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
