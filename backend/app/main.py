import uuid
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

from app.db.base import Base
from app.db.session import engine

from app.config import get_settings
from app.utils.logging import setup_logging, request_id_var, trace_id_var, get_logger
from app.utils.error_handler import create_error_response

settings = get_settings()
logger = setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    アプリケーション起動時と終了時のイベント処理
    """
    # Startup
    logger.info("Application startup")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
    
    yield
    
    # Shutdown
    logger.info("Application shutdown")
    engine.dispose()
    logger.info("Database connection closed")


# ===== FastAPI アプリケーション =====

app = FastAPI(
    title=settings.API_TITLE,
    description="Web広告・ランディングページ統合分析 API",
    version=settings.API_VERSION,
    lifespan=lifespan
)

# ===== CORS ミドルウェア =====

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== ミドルウェア: リクエスト ID / トレース ID =====
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """各リクエストに request_id / trace_id を付与"""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    
    request_id_var.set(request_id)
    trace_id_var.set(trace_id)
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = trace_id
    
    return response

# ===== 例外ハンドラ: Pydantic バリデーションエラー =====
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic バリデーションエラー処理"""
    error_response, status_code = create_error_response(
        error_message="Request validation failed",
        error_code="VALIDATION_ERROR",
        status_code=422,
        details={"errors": exc.errors()}
    )
    return JSONResponse(status_code=status_code, content=error_response)

# ===== 例外ハンドラ: HTTP 例外 =====
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 例外処理"""
    error_response, status_code = create_error_response(
        error_message=exc.detail,
        error_code="HTTP_ERROR",
        status_code=exc.status_code
    )
    return JSONResponse(status_code=status_code, content=error_response)

# ===== 例外ハンドラ: 汎用例外 =====
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """汎用例外処理"""
    error_response, status_code = create_error_response(
        error_message=str(exc),
        error_code="INTERNAL_ERROR",
        status_code=500,
        details={"exception_type": type(exc).__name__}
    )
    return JSONResponse(status_code=status_code, content=error_response)

# ===== ヘルスチェック =====
@app.get("/health", tags=["Health"])
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "healthy",
        "version": settings.API_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# ===== ルーター登録 =====
from app.api.routes import specs
app.include_router(specs.router)

logger.info("FastAPI application initialized")
