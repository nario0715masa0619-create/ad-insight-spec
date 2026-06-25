from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# SQLite ローカル DB URL
SQLALCHEMY_DATABASE_URL = "sqlite:///./ad_insight.db"

# エンジン生成
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 用
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
