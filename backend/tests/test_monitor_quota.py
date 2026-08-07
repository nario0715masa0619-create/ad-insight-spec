"""
招待制モニターベータの月間分析上限（会社単位・毎月1日リセット）のテスト。

specs.router のみをマウントした最小のFastAPIアプリ + インメモリSQLiteで検証する
（test_analyze_endpoint.pyのパターンを踏襲）。AnalysisOrchestrator.run()は
実I/Oを伴うためモックし、/analyze の上限チェックロジック自体のみを検証する。
"""
from datetime import datetime, timedelta
from unittest.mock import patch

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


def _make_company_and_user(db_session, monthly_analysis_limit, slug="quota-co"):
    company = MonitorCompany(name="Quota Co", slug=slug, monthly_analysis_limit=monthly_analysis_limit, is_active=True)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    user = MonitorUser(
        company_id=company.id, email=f"user@{slug}.example", password_hash="unused", is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return company, user


def _minimal_valid_spec_dict(asset_id):
    return {
        "input_metadata": {
            "mode": "file_only",
            "source_type": "local_file",
            "input_timestamp": "2026-07-10T00:00:00Z",
        },
        "asset_meta": {"asset_id": asset_id},
        "creative_core": {"format": "image_static"},
        "landing_page": None,
        "performance": None,
        "diagnostics": {
            "qualitative": {
                "creative_fatigue_risk": "low",
                "creative_fatigue_basis": "テスト用の根拠テキストです",
            },
        },
        "views": None,
        "_metadata": {
            "generated_at": "2026-07-10T00:00:00Z",
            "data_source": "local_file",
            "ai_model_version": "gpt-4o",
            "input_mode": "file_only",
        },
    }


def _post_analyze(client, asset_id="asset_quota_test"):
    spec_dict = _minimal_valid_spec_dict(asset_id)
    with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict):
        return client.post(
            "/api/v1/specs/analyze",
            files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
            data={"mode": "file_only"},
        )


class TestMonthlyQuota:
    def test_analyze_allowed_when_under_limit(self, db_session):
        company, user = _make_company_and_user(db_session, monthly_analysis_limit=2)
        client = _make_client(db_session, user)

        response = _post_analyze(client, asset_id="asset_under_limit")
        assert response.status_code == 200

    def test_analyze_blocked_when_limit_reached(self, db_session):
        company, user = _make_company_and_user(db_session, monthly_analysis_limit=2, slug="quota-blocked")
        # 上限(2件)まで既に使い切っている状態を直接DBに作る
        for i in range(2):
            db_session.add(
                AdInsight(
                    asset_id=f"asset_existing_{i}",
                    version=1,
                    format="image_static",
                    spec_data={},
                    company_id=company.id,
                )
            )
        db_session.commit()

        client = _make_client(db_session, user)
        with patch.object(specs_module.AnalysisOrchestrator, "run") as mock_run:
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "file_only"},
            )
            # 上限チェックはOrchestrator実行より前段で弾くため、重い処理は一切走らない
            mock_run.assert_not_called()

        assert response.status_code == 403
        # bareなFastAPI()にrouterだけをマウントしているため detail の下に入る
        # （test_analyze_endpoint.pyのMetaAdsCsvErrorテストと同じ事情）。
        body = response.json()["detail"]
        assert body["error_code"] == "MONTHLY_LIMIT_EXCEEDED"
        assert body["details"]["usage"] == {"used": 2, "limit": 2, "remaining": 0, "limit_reached": True}

    def test_quota_resets_at_month_boundary(self, db_session):
        """前月分の分析は当月のカウントに含まれず、毎月1日にリセットされたのと
        同じ挙動になること（実装は「当月1日以降」を都度集計するのみで、
        別途リセット処理は走らない設計）。"""
        company, user = _make_company_and_user(db_session, monthly_analysis_limit=1, slug="quota-reset")

        last_month = datetime.utcnow().replace(day=1) - timedelta(days=1)
        db_session.add(
            AdInsight(
                asset_id="asset_from_last_month",
                version=1,
                format="image_static",
                spec_data={},
                company_id=company.id,
                created_at=last_month,
            )
        )
        db_session.commit()

        client = _make_client(db_session, user)
        response = _post_analyze(client, asset_id="asset_this_month")
        assert response.status_code == 200

    def test_deleted_analyses_still_count_towards_quota(self, db_session):
        """論理削除しても当月の実施実績は消えない（削除して上限を回避できない）"""
        company, user = _make_company_and_user(db_session, monthly_analysis_limit=1, slug="quota-deleted")
        db_session.add(
            AdInsight(
                asset_id="asset_deleted",
                version=1,
                format="image_static",
                spec_data={},
                company_id=company.id,
                is_deleted=True,
            )
        )
        db_session.commit()

        client = _make_client(db_session, user)
        with patch.object(specs_module.AnalysisOrchestrator, "run") as mock_run:
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "file_only"},
            )
            mock_run.assert_not_called()
        assert response.status_code == 403
