"""
招待制モニターベータのデータ分離（他社の分析結果が一覧・詳細・削除のいずれにも
出てこない/操作できないこと）のテスト。

specs.router のみをマウントした最小のFastAPIアプリ + インメモリSQLiteで検証する。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models import MonitorCompany, MonitorUser
from app.models.ad_insight import AdInsight
from app.api.deps import get_current_user
from app.api.routes import specs as specs_module

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


def _make_client(db_session, user):
    app = FastAPI()
    app.include_router(specs_module.router)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    def _override_get_current_user():
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    return TestClient(app)


@pytest.fixture
def two_companies(db_session):
    company_a = MonitorCompany(name="Company A", slug="company-a", monthly_analysis_limit=100, is_active=True)
    company_b = MonitorCompany(name="Company B", slug="company-b", monthly_analysis_limit=100, is_active=True)
    db_session.add_all([company_a, company_b])
    db_session.commit()
    db_session.refresh(company_a)
    db_session.refresh(company_b)

    user_a = MonitorUser(company_id=company_a.id, email="a@example.com", password_hash="unused", is_active=True)
    user_b = MonitorUser(company_id=company_b.id, email="b@example.com", password_hash="unused", is_active=True)
    db_session.add_all([user_a, user_b])
    db_session.commit()
    db_session.refresh(user_a)
    db_session.refresh(user_b)

    # Company A が所有する分析結果を1件作成
    record_a = AdInsight(
        asset_id="asset_owned_by_a",
        version=1,
        format="image_static",
        spec_data={"asset_meta": {"asset_id": "asset_owned_by_a"}},
        company_id=company_a.id,
    )
    db_session.add(record_a)
    db_session.commit()

    return {"company_a": company_a, "company_b": company_b, "user_a": user_a, "user_b": user_b}


class TestCrossCompanyIsolation:
    def test_list_specs_only_returns_own_companys_records(self, db_session, two_companies):
        client_b = _make_client(db_session, two_companies["user_b"])
        response = client_b.get("/api/v1/specs/")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_list_specs_returns_own_records_for_owning_company(self, db_session, two_companies):
        client_a = _make_client(db_session, two_companies["user_a"])
        response = client_a.get("/api/v1/specs/")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["asset_meta"]["asset_id"] == "asset_owned_by_a"

    def test_get_spec_returns_404_for_other_companys_asset(self, db_session, two_companies):
        client_b = _make_client(db_session, two_companies["user_b"])
        response = client_b.get("/api/v1/specs/asset_owned_by_a")
        assert response.status_code == 404

    def test_get_spec_succeeds_for_owning_company(self, db_session, two_companies):
        client_a = _make_client(db_session, two_companies["user_a"])
        response = client_a.get("/api/v1/specs/asset_owned_by_a")
        assert response.status_code == 200

    def test_delete_spec_returns_404_and_does_not_delete_other_companys_asset(self, db_session, two_companies):
        client_b = _make_client(db_session, two_companies["user_b"])
        response = client_b.delete("/api/v1/specs/asset_owned_by_a")
        assert response.status_code == 404

        # Company A側からは引き続き参照できる（誤って削除されていない）ことを確認
        client_a = _make_client(db_session, two_companies["user_a"])
        get_response = client_a.get("/api/v1/specs/asset_owned_by_a")
        assert get_response.status_code == 200

    def test_delete_spec_succeeds_for_owning_company(self, db_session, two_companies):
        client_a = _make_client(db_session, two_companies["user_a"])
        response = client_a.delete("/api/v1/specs/asset_owned_by_a")
        assert response.status_code == 200
