"""
招待制モニターベータの月次クレジット上限（会社単位・毎月1日リセット・
「実行前チェック→成功時のみ消費確定」方式）のテスト。

specs.router のみをマウントした最小のFastAPIアプリ + インメモリSQLiteで検証する
（test_analyze_endpoint.pyのパターンを踏襲）。AnalysisOrchestrator.run()は
実I/Oを伴うためモックし、/analyze のクレジットチェック・消費ロジック自体のみを
検証する。
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
from app.models import MonitorCompany, MonitorUser, CreditUsageLog
from app.api.deps import get_current_user
from app.api.routes import specs as specs_module
from app.repositories import MonitorRepository

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


def _make_company_and_user(db_session, monthly_credit_limit, slug="quota-co"):
    company = MonitorCompany(name="Quota Co", slug=slug, monthly_credit_limit=monthly_credit_limit, is_active=True)
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


def _post_analyze(client, asset_id="asset_quota_test", mode="file_only", raise_error=None):
    spec_dict = _minimal_valid_spec_dict(asset_id)
    with patch.object(
        specs_module.AnalysisOrchestrator,
        "run",
        side_effect=raise_error,
        return_value=None if raise_error else spec_dict,
    ):
        return client.post(
            "/api/v1/specs/analyze",
            files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
            data={"mode": mode},
        )


class TestUnknownModeRejected:
    """未対応のmodeは、クレジットチェックより前に422で弾かれ、消費もされないこと
    （credit_cost_for_mode()自体は未知modeをLight扱いにフォールバックする設計を
    維持しつつ、APIの入力境界であるspecs.py::analyze()側で明示的に拒否する）。"""

    def test_unknown_mode_returns_422_without_running_orchestrator(self, db_session):
        company, user = _make_company_and_user(db_session, monthly_credit_limit=10, slug="unknown-mode-co")
        client = _make_client(db_session, user)

        with patch.object(specs_module.AnalysisOrchestrator, "run") as mock_run:
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "totally_unknown_mode"},
            )
            mock_run.assert_not_called()

        assert response.status_code == 422
        body = response.json()["detail"]
        assert body["error_code"] == "VALIDATION_ERROR"

        used = MonitorRepository(db_session).sum_credits_used_this_month(company.id)
        assert used == 0


class TestCreditConsumptionByMode:
    """分析タイプごとのクレジット消費（Light=1 / Standard=2 / Heavy=3）"""

    @pytest.mark.parametrize(
        "mode,expected_cost",
        [
            ("file_only", 1),
            ("file_plus_lp", 2),
            ("file_plus_lp_plus_manual_kpi", 3),
        ],
    )
    def test_successful_analysis_consumes_expected_credits(self, db_session, mode, expected_cost):
        company, user = _make_company_and_user(db_session, monthly_credit_limit=10, slug=f"tier-{mode}")
        client = _make_client(db_session, user)

        response = _post_analyze(client, asset_id=f"asset_{mode}", mode=mode)
        assert response.status_code == 200

        used = MonitorRepository(db_session).sum_credits_used_this_month(company.id)
        assert used == expected_cost


class TestMonthlyCreditQuota:
    def test_analyze_allowed_when_under_limit(self, db_session):
        company, user = _make_company_and_user(db_session, monthly_credit_limit=2)
        client = _make_client(db_session, user)

        response = _post_analyze(client, asset_id="asset_under_limit")
        assert response.status_code == 200

    def test_analyze_blocked_when_credits_already_exhausted(self, db_session):
        company, user = _make_company_and_user(db_session, monthly_credit_limit=2, slug="quota-blocked")
        # 上限(2クレジット)まで既に消費済みの状態を直接DBに作る
        db_session.add(
            CreditUsageLog(
                company_id=company.id, user_id=user.id, credit_cost=2, analysis_type="file_only"
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
        assert body["error_code"] == "MONTHLY_CREDIT_LIMIT_EXCEEDED"
        assert body["details"]["usage"] == {"used": 2, "limit": 2, "remaining": 0, "limit_reached": True}
        assert body["details"]["required_credits"] == 1

    def test_analyze_blocked_when_remaining_credits_below_required_cost(self, db_session):
        """残量はあるが、このモードが必要とするクレジット数には満たない場合も
        ブロックされること（used=0でも limit_reached=False になり得るケース）。"""
        company, user = _make_company_and_user(db_session, monthly_credit_limit=2, slug="quota-insufficient")
        db_session.add(
            CreditUsageLog(
                company_id=company.id, user_id=user.id, credit_cost=1, analysis_type="file_only"
            )
        )
        db_session.commit()  # used=1, limit=2 -> remaining=1, limit_reached=False だが heavy(3)は足りない

        client = _make_client(db_session, user)
        with patch.object(specs_module.AnalysisOrchestrator, "run") as mock_run:
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "file_plus_lp_plus_manual_kpi"},
            )
            mock_run.assert_not_called()

        assert response.status_code == 403
        body = response.json()["detail"]
        assert body["details"]["usage"]["limit_reached"] is False
        assert body["details"]["required_credits"] == 3

    def test_quota_resets_at_month_boundary(self, db_session):
        """前月分のクレジット消費は当月の集計に含まれず、毎月1日にリセットされたのと
        同じ挙動になること（実装は「当月1日以降」を都度集計するのみで、
        別途リセット処理は走らない設計）。"""
        company, user = _make_company_and_user(db_session, monthly_credit_limit=1, slug="quota-reset")

        last_month = datetime.utcnow().replace(day=1) - timedelta(days=1)
        db_session.add(
            CreditUsageLog(
                company_id=company.id,
                user_id=user.id,
                credit_cost=1,
                analysis_type="file_only",
                created_at=last_month,
            )
        )
        db_session.commit()

        client = _make_client(db_session, user)
        response = _post_analyze(client, asset_id="asset_this_month")
        assert response.status_code == 200

    def test_deleting_analysis_does_not_refund_credits(self, db_session):
        """論理削除しても消費済みクレジットは戻らない
        （credit_usage_logs は ad_insights.is_deleted と独立しているため）"""
        company, user = _make_company_and_user(db_session, monthly_credit_limit=1, slug="quota-no-refund")
        client = _make_client(db_session, user)

        response = _post_analyze(client, asset_id="asset_to_delete")
        assert response.status_code == 200

        delete_response = client.delete("/api/v1/specs/asset_to_delete")
        assert delete_response.status_code == 200

        # 削除後も当月の消費量は減らないため、上限(1)に達したままブロックされる
        second_response = _post_analyze(client, asset_id="asset_after_delete")
        assert second_response.status_code == 403

    def test_failed_analysis_does_not_consume_credits(self, db_session):
        """AnalysisOrchestrator.run() が例外を送出した場合、クレジットは
        一切消費されないこと（予約状態を持たず、成功時のみ消費確定する設計）。"""
        company, user = _make_company_and_user(db_session, monthly_credit_limit=5, slug="quota-fail-no-consume")
        client = _make_client(db_session, user)

        response = _post_analyze(client, asset_id="asset_will_fail", raise_error=RuntimeError("boom"))
        assert response.status_code == 500

        used = MonitorRepository(db_session).sum_credits_used_this_month(company.id)
        assert used == 0

        # 消費されていないので、直後の正常な分析は引き続き実行できる
        success_response = _post_analyze(client, asset_id="asset_after_failure")
        assert success_response.status_code == 200
        assert MonitorRepository(db_session).sum_credits_used_this_month(company.id) == 1


class TestPlanBasedQuotaIntegration:
    """会社が個別上書きを持たず、プランに紐づいている場合でも /analyze の
    クレジットチェックが正しくプランの上限を使うことのエンドツーエンド確認
    （resolve_monthly_credit_limitの単体テストはtest_pricing_plans.py参照）。"""

    def test_analyze_respects_plan_limit_when_no_override(self, db_session):
        repo = MonitorRepository(db_session)
        plan = repo.create_plan(code="growth-quota", name="Growth", monthly_credit_limit=1)
        company, user = _make_company_and_user(db_session, monthly_credit_limit=None, slug="plan-quota-co")
        repo.update_company(company.id, plan_id=plan.id)
        db_session.refresh(company)

        client = _make_client(db_session, user)

        first_response = _post_analyze(client, asset_id="asset_plan_quota_1")
        assert first_response.status_code == 200

        second_response = _post_analyze(client, asset_id="asset_plan_quota_2")
        assert second_response.status_code == 403
        body = second_response.json()["detail"]
        assert body["error_code"] == "MONTHLY_CREDIT_LIMIT_EXCEEDED"
        assert body["details"]["usage"]["limit"] == 1
