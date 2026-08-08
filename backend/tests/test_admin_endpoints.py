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
    company = MonitorCompany(name="Seed Co", slug="seed-co", monthly_credit_limit=50, is_active=True)
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
            "/api/v1/admin/companies", json={"name": "Acme Inc", "slug": "acme", "monthly_credit_limit": 30}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == "acme"
        assert body["monthly_credit_limit"] == 30
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
        response = client.patch(f"/api/v1/admin/companies/{company_id}", json={"monthly_credit_limit": 100})
        assert response.status_code == 200
        assert response.json()["monthly_credit_limit"] == 100

    def test_admin_can_deactivate_company(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.patch(f"/api/v1/admin/companies/{company_id}", json={"is_active": False})
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_nonexistent_company_returns_404(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.patch("/api/v1/admin/companies/999999", json={"monthly_credit_limit": 10})
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


class TestPlanManagement:
    def test_non_admin_cannot_create_plan(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["regular_user"])
        response = client.post(
            "/api/v1/admin/plans", json={"code": "starter", "name": "Starter", "monthly_credit_limit": 100}
        )
        assert response.status_code == 403

    def test_admin_can_create_plan(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.post(
            "/api/v1/admin/plans",
            json={
                "code": "pro",
                "name": "Pro",
                "monthly_credit_limit": 650,
                "monthly_price_jpy": 149800,
                "marketing_note": "初期導入企業向けキャンペーン企画中",
                "display_order": 3,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "pro"
        assert body["monthly_credit_limit"] == 650
        assert body["monthly_price_jpy"] == 149800
        assert body["marketing_note"] == "初期導入企業向けキャンペーン企画中"
        assert body["is_public"] is True
        assert body["is_active"] is True

    def test_create_plan_duplicate_code_returns_conflict(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        client.post("/api/v1/admin/plans", json={"code": "growth", "name": "Growth", "monthly_credit_limit": 300})
        response = client.post(
            "/api/v1/admin/plans", json={"code": "growth", "name": "Growth v2", "monthly_credit_limit": 350}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "PLAN_CODE_TAKEN"

    def test_enterprise_plan_can_omit_price_for_individual_quote(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.post(
            "/api/v1/admin/plans",
            json={"code": "enterprise", "name": "Enterprise", "monthly_credit_limit": 2000, "is_public": False},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["monthly_price_jpy"] is None
        assert body["is_public"] is False

    def test_admin_can_list_plans(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        client.post("/api/v1/admin/plans", json={"code": "starter", "name": "Starter", "monthly_credit_limit": 100})
        client.post("/api/v1/admin/plans", json={"code": "growth", "name": "Growth", "monthly_credit_limit": 300})

        response = client.get("/api/v1/admin/plans")
        assert response.status_code == 200
        codes = {p["code"] for p in response.json()}
        assert codes == {"starter", "growth"}

    def test_admin_can_update_plan_marketing_note_and_credits(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        create_response = client.post(
            "/api/v1/admin/plans", json={"code": "pro", "name": "Pro", "monthly_credit_limit": 650}
        )
        plan_id = create_response.json()["id"]

        response = client.patch(
            f"/api/v1/admin/plans/{plan_id}",
            json={"monthly_credit_limit": 700, "marketing_note": "初期導入企業向けキャンペーン企画中"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["monthly_credit_limit"] == 700
        assert body["marketing_note"] == "初期導入企業向けキャンペーン企画中"

    def test_admin_can_deactivate_plan(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        create_response = client.post(
            "/api/v1/admin/plans", json={"code": "legacy", "name": "Legacy", "monthly_credit_limit": 50}
        )
        plan_id = create_response.json()["id"]

        response = client.patch(f"/api/v1/admin/plans/{plan_id}", json={"is_active": False})
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_nonexistent_plan_returns_404(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.patch("/api/v1/admin/plans/999999", json={"monthly_credit_limit": 10})
        assert response.status_code == 404


class TestCompanyPlanAssignment:
    def test_create_company_with_plan_and_no_override_inherits_plan_limit(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        plan_id = client.post(
            "/api/v1/admin/plans", json={"code": "growth", "name": "Growth", "monthly_credit_limit": 300}
        ).json()["id"]

        response = client.post(
            "/api/v1/admin/companies", json={"name": "Plan Co", "slug": "plan-co", "plan_id": plan_id}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["monthly_credit_limit"] is None
        assert body["plan"]["code"] == "growth"
        assert body["usage_this_month"]["limit"] == 300
        assert body["limit_source"] == "plan:growth"

    def test_create_company_with_override_and_plan_uses_override(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        plan_id = client.post(
            "/api/v1/admin/plans", json={"code": "growth2", "name": "Growth", "monthly_credit_limit": 300}
        ).json()["id"]

        response = client.post(
            "/api/v1/admin/companies",
            json={"name": "Override Co", "slug": "override-co", "plan_id": plan_id, "monthly_credit_limit": 999},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["monthly_credit_limit"] == 999
        assert body["usage_this_month"]["limit"] == 999
        assert body["limit_source"] == "override"

    def test_create_company_with_unknown_plan_id_returns_404(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        response = client.post(
            "/api/v1/admin/companies", json={"name": "Bad Plan Co", "slug": "bad-plan-co", "plan_id": 999999}
        )
        assert response.status_code == 404

    def test_assign_plan_to_existing_company_via_patch(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        plan_id = client.post(
            "/api/v1/admin/plans", json={"code": "pro-assign", "name": "Pro", "monthly_credit_limit": 650}
        ).json()["id"]
        company_id = seed_company_and_users["company"].id  # created with monthly_credit_limit=50 override

        response = client.patch(f"/api/v1/admin/companies/{company_id}", json={"plan_id": plan_id})
        assert response.status_code == 200
        body = response.json()
        assert body["plan"]["code"] == "pro-assign"
        # 既存の個別上書き(50)が残っているため、プランではなく上書きが優先される
        assert body["usage_this_month"]["limit"] == 50

    def test_clear_credit_limit_override_falls_back_to_assigned_plan(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        plan_id = client.post(
            "/api/v1/admin/plans", json={"code": "growth3", "name": "Growth", "monthly_credit_limit": 300}
        ).json()["id"]
        company_id = seed_company_and_users["company"].id

        client.patch(f"/api/v1/admin/companies/{company_id}", json={"plan_id": plan_id})
        response = client.patch(
            f"/api/v1/admin/companies/{company_id}", json={"clear_credit_limit_override": True}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["monthly_credit_limit"] is None
        assert body["usage_this_month"]["limit"] == 300
        assert body["limit_source"] == "plan:growth3"

    def test_update_company_with_unknown_plan_id_returns_404(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        response = client.patch(f"/api/v1/admin/companies/{company_id}", json={"plan_id": 999999})
        assert response.status_code == 404

    def test_limit_source_is_fallback_when_no_plan_and_no_override(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        company_id = seed_company_and_users["company"].id
        client.patch(f"/api/v1/admin/companies/{company_id}", json={"clear_credit_limit_override": True})

        response = client.get("/api/v1/admin/companies")
        body = next(c for c in response.json() if c["id"] == company_id)
        assert body["limit_source"] == "fallback"
        assert body["usage_this_month"]["limit"] == 100  # DEFAULT_MONTHLY_CREDIT_LIMIT

    def test_limit_source_shows_inactive_when_assigned_plan_is_deactivated(self, db_session, seed_company_and_users):
        client = _make_client(db_session, seed_company_and_users["admin_user"])
        plan_id = client.post(
            "/api/v1/admin/plans", json={"code": "growth-deact", "name": "Growth", "monthly_credit_limit": 300}
        ).json()["id"]
        company_id = seed_company_and_users["company"].id
        client.patch(f"/api/v1/admin/companies/{company_id}", json={"plan_id": plan_id, "clear_credit_limit_override": True})
        client.patch(f"/api/v1/admin/plans/{plan_id}", json={"is_active": False})

        response = client.get("/api/v1/admin/companies")
        body = next(c for c in response.json() if c["id"] == company_id)
        assert body["limit_source"] == "plan:growth-deact(inactive)"
        assert body["plan"] is None  # 無効なプランはeffective_planとしては返さない
        assert body["usage_this_month"]["limit"] == 100  # フォールバックに落ちる
