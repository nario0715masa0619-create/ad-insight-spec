"""
app.main の共通例外ハンドラのテスト（回帰防止）。

Postgresスモークテストで発見: Pydanticのmodel_validatorがValueErrorをraiseすると、
FastAPIのRequestValidationError.errors()が ctx.error に生の例外インスタンスを
含むことがあり、main.pyのvalidation_exception_handlerがそれをそのまま
JSONResponse(content=...)に渡していたため、json.dumpsでのシリアライズに失敗して
本来422で返すべきところが500になっていた（TypeError: Object of type ValueError
is not JSON serializable）。

app.main.app（main.pyに登録された実際のexception handler群）を使う必要があるため、
他のエンドポイントテスト（test_analyze_endpoint.py等）のような「routerだけを
マウントした素のFastAPI()」パターンは使わない。lifespanが実DBのengineに対して
Base.metadata.create_all()を実行してしまう（get_dbのオーバーライドでは防げない）
副作用を避けるため、TestClient(app)は `with` コンテキストマネージャとしては
使わない（lifespanイベントを起動させない）。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models import VerificationCase, VerificationSuggestionEvaluation, VerificationFollowup  # noqa: F401
from app.models.ad_insight import AdInsight  # noqa: F401
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    # lifespan（実engineへの Base.metadata.create_all）を起動させないよう、
    # `with TestClient(app) as client:` は使わない。
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_asset_id_without_asset_version_returns_422_not_500(client):
    """
    model_validatorがValueErrorを投げるケースで、500ではなく422が返ること
    （jsonable_encoder修正の回帰防止テスト）。
    """
    response = client.post(
        "/api/v1/verification/cases",
        json={"case_name": "asset_version欠落テスト", "asset_id": "asset_x"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    # errors 配下がJSONとして正しくパースできる（=シリアライズに成功している）ことの確認
    assert isinstance(body["details"]["errors"], list)
    assert len(body["details"]["errors"]) >= 1


def test_asset_id_with_asset_version_saves_successfully(client):
    response = client.post(
        "/api/v1/verification/cases",
        json={"case_name": "正常系", "asset_id": "asset_x", "asset_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["asset_id"] == "asset_x"
    assert response.json()["asset_version"] == 1


def test_existing_specs_list_endpoint_unaffected(client):
    response = client.get("/api/v1/specs/")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "skip": 0, "limit": 10}


def test_health_endpoint_unaffected(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
