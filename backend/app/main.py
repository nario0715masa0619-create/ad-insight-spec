from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.db.base import Base
from app.db.session import engine

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Lifespan イベント =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    アプリケーション起動時と終了時のイベント処理
    
    startup: DB テーブル作成
    shutdown: リソースクリーンアップ
    """
    # Startup
    logger.info("Starting up application...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    engine.dispose()
    logger.info("Database connection closed")


# ===== FastAPI アプリケーション =====

app = FastAPI(
    title="Ad-Insight-Spec API",
    description="Web広告・ランディングページ統合分析 API",
    version="0.2.0",
    lifespan=lifespan
)

# ===== CORS ミドルウェア =====

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発用: すべてのオリジンを許可 (本番環境では制限が必要)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== ヘルスチェック =====

@app.get("/health", tags=["Health"])
def health_check():
    """
    ヘルスチェック用エンドポイント
    
    Returns:
        {"status": "ok"}
    """
    return {"status": "ok"}


# ===== ルーター登録 =====

# API v1 ルーター
from app.api.routes import specs
app.include_router(specs.router)

logger.info("FastAPI application initialized")
