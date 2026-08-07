"""
招待制モニターベータの管理API(/api/v1/admin/*)のテスト。

require_admin（is_admin=Trueのログイン済みユーザーのみ）で保護されていることと、
会社/ユーザーのCRUDが最低限動くことを検証する。
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
from app.api.deps import get_current_user
from app.api.routes import admin as admin_module

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
    app.include_router(admin_module.router)

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
def seed_company_and_users(db_session):
    company = MonitorCompany(name="Seed Co", slug="seed-co", monthly_analysis_limit=50, is_active=True)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    admin_user = MonitorUser(
        company_id=company.id, email="admin@seed.example", password_hash="unused", is_active=True, is_admin=True
    )
    regular_user = MonitorUser(
        company_id=company.id, email="regular@seed.example", password_hash="unused", is_active=True, is_admin=False
    )
    db_session.add_all([admin_user, regular_user])
    db_session.commit()
    db_session.refresh(admin_user)
    db_session.refresh(regular_user)
    return {"company": company, "admin_user": admin_user, "regular_user": regular_user}


class TestAdminAuthorization:
    def test_non_admin_cannot_create_company(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["regular_user"])
        response = client.post("/api/v1/admin/companies", json={"name": "New Co", "slug": "new-co"})
        assert response.status_code == 403
        # bareなFastAPI()にrouterだけをマウントしているため detail の下に入る
        assert response.json()["detail"]["error_code"] == "ADMIN_REQUIRED"

    def test_non_admin_cannot_list_companies(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["regular_user"])
        response = client.get("/api/v1/admin/companies")
        assert response.status_code == 403


class TestCompanyManagement:
    def test_admin_can_create_company(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.post(
            "/api/v1/admin/companies", json={"name": "Acme Inc", "slug": "acme", "monthly_analysis_limit": 30}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == "acme"
        assert body["monthly_analysis_limit"] == 30
        assert body["usage_this_month"] == {"used": 0, "limit": 30, "remaining": 30, "limit_reached": False}

    def test_create_company_duplicate_slug_returns_conflict(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.post(
            "/api/v1/admin/companies", json={"name": "Duplicate", "slug": "seed-co"}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "COMPANY_SLUG_TAKEN"

    def test_admin_can_update_company_limit(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.patch(f"/api/v1/admin/companies/{company_id}", json={"monthly_analysis_limit": 100})
        assert response.status_code == 200
        assert response.json()["monthly_analysis_limit"] == 100

    def test_admin_can_deactivate_company(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.patch(f"/api/v1/admin/companies/{company_id}", json={"is_active": False})
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_nonexistent_company_returns_404(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.patch("/api/v1/admin/companies/999999", json={"monthly_analysis_limit": 10})
        assert response.status_code == 404


class TestUserManagement:
    def test_admin_can_invite_user_with_generated_password(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.post(
            "/api/v1/admin/users", json={"company_id": company_id, "email": "newbie@seed.example"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "newbie@seed.example"
        assert body["is_active"] is True
        assert "generated_password" in body and len(body["generated_password"]) > 0

    def test_create_user_duplicate_email_returns_conflict(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.post(
            "/api/v1/admin/users",
            json={"company_id": company_id, "email": seed_company_and_users["regular_user"].email},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "USER_EMAIL_TAKEN"

    def test_create_user_for_nonexistent_company_returns_404(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.post(
            "/api/v1/admin/users", json={"company_id": 999999, "email": "orphan@example.com"}
        )
        assert response.status_code == 404

    def test_admin_can_deactivate_user(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        user_id = seed_company_and_users["regular_user"].id
        response = client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False})
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_admin_can_list_users_filtered_by_company(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.get(f"/api/v1/admin/users?company_id={company_id}")
        assert response.status_code == 200
        emails = {u["email"] for u in response.json()}
        assert emails == {"admin@seed.example", "regular@seed.example"}
