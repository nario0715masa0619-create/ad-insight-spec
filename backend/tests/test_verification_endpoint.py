"""
/api/v1/verification/* エンドポイントのテスト。

verification.routerだけをマウントした最小のFastAPIアプリ + インメモリSQLiteで検証する
（test_analyze_endpoint.pyのDB/TestClientセットアップパターンを踏襲）。
既存の /api/v1/specs/* を一切変更していないことは test_analyze_endpoint.py 側で担保される。
"""
import csv
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models import (  # noqa: F401
    VerificationCase,
    VerificationSuggestionEvaluation,
    VerificationFollowup,
    MonitorCompany,
    MonitorUser,
)
from app.api.deps import get_current_user
from app.api.routes import verification as verification_module

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
def test_user(db_session):
    """招待制モニターベータ導入により verification API 全体がログイン必須になったため、
    テスト用の会社・ユーザーを1件用意し、get_current_user を差し替える。"""
    company = MonitorCompany(name="Test Co", slug="test-co", monthly_credit_limit=100000, is_active=True)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    user = MonitorUser(
        company_id=company.id,
        email="tester@example.com",
        password_hash="unused-in-tests",
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session, test_user):
    app = FastAPI()
    app.include_router(verification_module.router)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    def _override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    return TestClient(app)


def _create_case(client, case_name="株式会社サンプル", asset_id="asset_0001", asset_version=1):
    response = client.post(
        "/api/v1/verification/cases",
        json={
            "case_name": case_name,
            "asset_id": asset_id,
            "asset_version": asset_version if asset_id else None,
            "pre_hearing_notes": {"industry": "EC", "current_issue": "CVR低下"},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_and_get_case(client):
    created = _create_case(client)
    case_id = created["id"]
    assert created["asset_version"] == 1
    assert created["pre_hearing_notes"]["industry"] == "EC"
    assert created["suggestion_evaluations"] == []

    response = client.get(f"/api/v1/verification/cases/{case_id}")
    assert response.status_code == 200
    assert response.json()["case_name"] == "株式会社サンプル"


def test_create_case_without_asset_id_or_version(client):
    response = client.post(
        "/api/v1/verification/cases",
        json={"case_name": "asset_idなし案件", "pre_hearing_notes": None},
    )
    assert response.status_code == 200
    assert response.json()["asset_id"] is None
    assert response.json()["asset_version"] is None


def test_create_case_with_asset_id_but_no_version_is_rejected(client):
    response = client.post(
        "/api/v1/verification/cases",
        json={"case_name": "バージョン欠落案件", "asset_id": "asset_x", "pre_hearing_notes": None},
    )
    assert response.status_code == 422


def test_create_case_with_asset_version_but_no_asset_id_is_rejected(client):
    response = client.post(
        "/api/v1/verification/cases",
        json={"case_name": "asset_id欠落案件", "asset_version": 1, "pre_hearing_notes": None},
    )
    assert response.status_code == 422


def test_get_case_404(client):
    response = client.get("/api/v1/verification/cases/999999")
    assert response.status_code == 404


def test_list_cases_pagination_and_suggestion_count(client):
    case1 = _create_case(client, case_name="案件1")
    _create_case(client, case_name="案件2")

    client.post(
        f"/api/v1/verification/cases/{case1['id']}/suggestions",
        json={
            "suggestion_key": "LPのCTAを変更",
            "suggestion_text": "CTAボタンの文言を変更する提案",
            "awareness_rating": "realized_when_told",
            "originality_rating": "could_not_have_suggested_myself",
        },
    )

    response = client.get("/api/v1/verification/cases", params={"skip": 0, "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    case1_item = next(i for i in body["items"] if i["id"] == case1["id"])
    assert case1_item["suggestion_count"] == 1


def test_update_presentation_evaluation(client):
    case = _create_case(client)
    response = client.patch(
        f"/api/v1/verification/cases/{case['id']}/presentation-evaluation",
        json={"presentation_evaluation": {"usefulness": "high", "comment": "有益だった"}},
    )
    assert response.status_code == 200
    assert response.json()["presentation_evaluation"]["usefulness"] == "high"


def test_suggestion_evaluation_and_followup_flow(client):
    case = _create_case(client)
    case_id = case["id"]

    add_response = client.post(
        f"/api/v1/verification/cases/{case_id}/suggestions",
        json={
            "suggestion_key": "配信面の見直し",
            "suggestion_text": "Audience Networkを除外する提案",
            "awareness_rating": "realized_when_told",
            "originality_rating": "could_not_have_suggested_myself",
        },
    )
    assert add_response.status_code == 200
    suggestion = add_response.json()
    suggestion_id = suggestion["id"]

    update_response = client.patch(
        f"/api/v1/verification/cases/{case_id}/suggestions/{suggestion_id}",
        json={"awareness_rating": "already_knew"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["awareness_rating"] == "already_knew"
    assert update_response.json()["originality_rating"] == "could_not_have_suggested_myself"

    week2_response = client.put(
        f"/api/v1/verification/suggestions/{suggestion_id}/followups/week_2",
        json={"executed": True, "result_change": "CPA 10%改善"},
    )
    assert week2_response.status_code == 200
    assert week2_response.json()["checkpoint"] == "week_2"

    week4_response = client.put(
        f"/api/v1/verification/suggestions/{suggestion_id}/followups/week_4",
        json={"executed": True, "result_change": "CPA 15%改善"},
    )
    assert week4_response.status_code == 200

    detail_response = client.get(f"/api/v1/verification/cases/{case_id}")
    detail = detail_response.json()
    assert len(detail["suggestion_evaluations"]) == 1
    followups = detail["suggestion_evaluations"][0]["followups"]
    assert {f["checkpoint"] for f in followups} == {"week_2", "week_4"}


def test_upsert_followup_invalid_checkpoint(client):
    case = _create_case(client)
    add_response = client.post(
        f"/api/v1/verification/cases/{case['id']}/suggestions",
        json={
            "suggestion_key": "テスト提案",
            "awareness_rating": "already_knew",
            "originality_rating": "generic",
        },
    )
    suggestion_id = add_response.json()["id"]

    response = client.put(
        f"/api/v1/verification/suggestions/{suggestion_id}/followups/week_1",
        json={"executed": True},
    )
    assert response.status_code == 400


def test_add_suggestion_evaluation_404_for_missing_case(client):
    response = client.post(
        "/api/v1/verification/cases/999999/suggestions",
        json={
            "suggestion_key": "テスト提案",
            "awareness_rating": "already_knew",
            "originality_rating": "generic",
        },
    )
    assert response.status_code == 404


def test_export_csv_contains_expected_rows(client):
    case = _create_case(client, case_name="CSV検証案件")
    add_response = client.post(
        f"/api/v1/verification/cases/{case['id']}/suggestions",
        json={
            "suggestion_key": "配信面の見直し",
            "suggestion_text": "Audience Networkを除外する提案",
            "awareness_rating": "realized_when_told",
            "originality_rating": "could_not_have_suggested_myself",
        },
    )
    suggestion_id = add_response.json()["id"]
    client.put(
        f"/api/v1/verification/suggestions/{suggestion_id}/followups/week_2",
        json={"executed": True, "result_change": "CPA 10%改善"},
    )

    response = client.get("/api/v1/verification/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    content = response.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["case_name"] == "CSV検証案件"
    assert rows[0]["asset_version"] == "1"
    assert rows[0]["suggestion_key"] == "配信面の見直し"
    assert rows[0]["week_2_result_change"] == "CPA 10%改善"
    assert rows[0]["week_4_result_change"] == ""
