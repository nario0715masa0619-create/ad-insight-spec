"""
価格・プラン定義の外出し化（PricingPlan）のテスト。

MonitorRepository の実効クレジット上限解決ロジック
（会社個別上書き > プラン > フォールバック）を、DB直結のユニットテストとして検証する。
HTTP経由の管理APIテストは test_admin_endpoints.py 側で扱う。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import MonitorCompany
from app.repositories.monitor_repository import MonitorRepository, DEFAULT_MONTHLY_CREDIT_LIMIT

# backend/tests/ -> backend/ -> repo root -> scripts/seed_data/pricing_plans.json
SEED_DATA_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed_data" / "pricing_plans.json"

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
def repo(db_session):
    return MonitorRepository(db_session)


def _make_company(repo, **overrides):
    defaults = {"name": "Test Co", "slug": f"co-{id(overrides)}"}
    defaults.update(overrides)
    return repo.create_company(**defaults)


class TestResolutionPriority:
    def test_company_override_wins_over_plan(self, repo):
        plan = repo.create_plan(code="growth", name="Growth", monthly_credit_limit=300)
        company = _make_company(repo, slug="override-wins", monthly_credit_limit=42, plan_id=plan.id)

        assert repo.resolve_monthly_credit_limit(company) == 42

    def test_plan_used_when_no_override(self, repo):
        plan = repo.create_plan(code="pro", name="Pro", monthly_credit_limit=650)
        company = _make_company(repo, slug="plan-only", monthly_credit_limit=None, plan_id=plan.id)

        assert repo.resolve_monthly_credit_limit(company) == 650

    def test_fallback_used_when_neither_override_nor_plan(self, repo):
        company = _make_company(repo, slug="fallback-only", monthly_credit_limit=None, plan_id=None)

        assert repo.resolve_monthly_credit_limit(company) == DEFAULT_MONTHLY_CREDIT_LIMIT

    def test_fallback_used_when_plan_id_set_but_plan_missing(self, repo, db_session):
        """整合性が壊れて存在しないplan_idを指しているケースでも例外を出さずフォールバックする"""
        company = _make_company(repo, slug="dangling-plan", monthly_credit_limit=None, plan_id=999999)

        assert repo.resolve_monthly_credit_limit(company) == DEFAULT_MONTHLY_CREDIT_LIMIT


class TestPlanEffectiveness:
    def test_inactive_plan_is_ignored(self, repo):
        plan = repo.create_plan(code="starter", name="Starter", monthly_credit_limit=100)
        repo.update_plan(plan.id, is_active=False)
        company = _make_company(repo, slug="inactive-plan", monthly_credit_limit=None, plan_id=plan.id)

        assert repo.get_effective_plan(company) is None
        assert repo.resolve_monthly_credit_limit(company) == DEFAULT_MONTHLY_CREDIT_LIMIT

    def test_plan_not_yet_effective_is_ignored(self, repo):
        future = datetime.utcnow() + timedelta(days=30)
        plan = repo.create_plan(code="future-plan", name="Future", monthly_credit_limit=500, effective_from=future)
        company = _make_company(repo, slug="future-plan-co", monthly_credit_limit=None, plan_id=plan.id)

        assert repo.get_effective_plan(company) is None
        assert repo.resolve_monthly_credit_limit(company) == DEFAULT_MONTHLY_CREDIT_LIMIT

    def test_expired_plan_is_ignored(self, repo):
        past = datetime.utcnow() - timedelta(days=1)
        plan = repo.create_plan(code="expired-plan", name="Expired", monthly_credit_limit=500, effective_to=past)
        company = _make_company(repo, slug="expired-plan-co", monthly_credit_limit=None, plan_id=plan.id)

        assert repo.get_effective_plan(company) is None
        assert repo.resolve_monthly_credit_limit(company) == DEFAULT_MONTHLY_CREDIT_LIMIT

    def test_plan_within_effective_window_is_used(self, repo):
        past = datetime.utcnow() - timedelta(days=1)
        future = datetime.utcnow() + timedelta(days=1)
        plan = repo.create_plan(
            code="current-plan", name="Current", monthly_credit_limit=500, effective_from=past, effective_to=future
        )
        company = _make_company(repo, slug="current-plan-co", monthly_credit_limit=None, plan_id=plan.id)

        assert repo.resolve_monthly_credit_limit(company) == 500


class TestUsageSummaryIntegratesResolvedLimit:
    def test_get_usage_summary_uses_plan_limit(self, repo):
        plan = repo.create_plan(code="growth2", name="Growth", monthly_credit_limit=10)
        company = _make_company(repo, slug="usage-plan", monthly_credit_limit=None, plan_id=plan.id)
        repo.record_credit_usage(company_id=company.id, user_id=1, credit_cost=3, analysis_type="file_only")

        usage = repo.get_usage_summary(company)
        assert usage == {"used": 3, "limit": 10, "remaining": 7, "limit_reached": False}

    def test_has_sufficient_credits_respects_plan_limit(self, repo):
        plan = repo.create_plan(code="pro2", name="Pro", monthly_credit_limit=3)
        company = _make_company(repo, slug="sufficient-plan", monthly_credit_limit=None, plan_id=plan.id)
        repo.record_credit_usage(company_id=company.id, user_id=1, credit_cost=2, analysis_type="file_only")

        assert repo.has_sufficient_credits(company, credit_cost=1) is True
        assert repo.has_sufficient_credits(company, credit_cost=2) is False


class TestClearOverride:
    def test_clear_credit_limit_override_falls_back_to_plan(self, repo):
        plan = repo.create_plan(code="growth3", name="Growth", monthly_credit_limit=300)
        company = _make_company(repo, slug="clear-override", monthly_credit_limit=999, plan_id=plan.id)
        assert repo.resolve_monthly_credit_limit(company) == 999

        updated = repo.update_company(company.id, clear_credit_limit_override=True)
        assert updated.monthly_credit_limit is None
        assert repo.resolve_monthly_credit_limit(updated) == 300


class TestDescribeLimitSource:
    """CLI(manage_monitor_accounts.py)とAdmin API(admin.py)の両方が共有する
    MonitorRepository.describe_limit_source() のテスト（レビュー指摘: 二重実装の解消）。"""

    def test_override_takes_precedence(self, repo):
        plan = repo.create_plan(code="growth-src", name="Growth", monthly_credit_limit=300)
        company = _make_company(repo, slug="src-override", monthly_credit_limit=50, plan_id=plan.id)
        assert repo.describe_limit_source(company) == "override"

    def test_zero_override_is_still_reported_as_override(self, repo):
        """0は「上書きなし」ではなく明示的な上書き値として扱われること
        （company.monthly_credit_limit is not None で判定しているため）。"""
        company = _make_company(repo, slug="src-zero-override", monthly_credit_limit=0, plan_id=None)
        assert repo.describe_limit_source(company) == "override"

    def test_plan_reported_when_no_override(self, repo):
        plan = repo.create_plan(code="pro-src", name="Pro", monthly_credit_limit=650)
        company = _make_company(repo, slug="src-plan", monthly_credit_limit=None, plan_id=plan.id)
        assert repo.describe_limit_source(company) == "plan:pro-src"

    def test_inactive_plan_reported_distinctly(self, repo):
        plan = repo.create_plan(code="legacy-src", name="Legacy", monthly_credit_limit=100)
        repo.update_plan(plan.id, is_active=False)
        company = _make_company(repo, slug="src-inactive", monthly_credit_limit=None, plan_id=plan.id)
        assert repo.describe_limit_source(company) == "plan:legacy-src(inactive)"

    def test_dangling_plan_id_reported_with_placeholder(self, repo):
        company = _make_company(repo, slug="src-dangling", monthly_credit_limit=None, plan_id=999999)
        assert repo.describe_limit_source(company) == "plan:?(inactive)"

    def test_fallback_when_neither_override_nor_plan(self, repo):
        company = _make_company(repo, slug="src-fallback", monthly_credit_limit=None, plan_id=None)
        assert repo.describe_limit_source(company) == "fallback"


class TestPlanCrud:
    def test_create_and_get_plan_by_code(self, repo):
        plan = repo.create_plan(
            code="enterprise",
            name="Enterprise",
            monthly_credit_limit=1000,
            monthly_price_jpy=None,
            marketing_note="個別見積",
            is_public=False,
        )
        fetched = repo.get_plan_by_code("enterprise")
        assert fetched is not None
        assert fetched.id == plan.id
        assert fetched.monthly_price_jpy is None
        assert fetched.is_public is False

    def test_list_plans_ordered_by_display_order(self, repo):
        repo.create_plan(code="c", name="C", monthly_credit_limit=1, display_order=2)
        repo.create_plan(code="a", name="A", monthly_credit_limit=1, display_order=0)
        repo.create_plan(code="b", name="B", monthly_credit_limit=1, display_order=1)

        codes = [p.code for p in repo.list_plans()]
        assert codes == ["a", "b", "c"]

    def test_list_plans_public_only_filter(self, repo):
        repo.create_plan(code="public-plan", name="Public", monthly_credit_limit=1, is_public=True)
        repo.create_plan(code="monitor-plan", name="Monitor", monthly_credit_limit=1, is_public=False)

        public_codes = [p.code for p in repo.list_plans(public_only=True)]
        assert public_codes == ["public-plan"]

    def test_update_plan_marketing_note(self, repo):
        plan = repo.create_plan(code="pro3", name="Pro", monthly_credit_limit=650, monthly_price_jpy=149800)
        updated = repo.update_plan(plan.id, marketing_note="初期導入企業向けキャンペーン企画中")
        assert updated.marketing_note == "初期導入企業向けキャンペーン企画中"
        # 他のフィールドは変更していないこと
        assert updated.monthly_price_jpy == 149800

    def test_update_plan_clear_price(self, repo):
        plan = repo.create_plan(code="quote-plan", name="Quote", monthly_credit_limit=1, monthly_price_jpy=50000)
        updated = repo.update_plan(plan.id, clear_monthly_price_jpy=True)
        assert updated.monthly_price_jpy is None


class TestUpsertPlanByCode:
    """初期プランseed（scripts/manage_monitor_accounts.py seed-plans）が使う
    冪等upsertのテスト。update_plan()のPATCH的な部分更新とは異なり、渡した値を
    そのプランの完全な望ましい状態として扱う（＝フル置換）ことを確認する。"""

    def test_creates_when_missing(self, repo):
        plan = repo.upsert_plan_by_code(code="starter", name="Starter", monthly_credit_limit=100)
        assert plan.code == "starter"
        assert repo.get_plan_by_code("starter").id == plan.id

    def test_rerun_is_idempotent_no_duplicate_rows(self, repo):
        repo.upsert_plan_by_code(code="growth", name="Growth", monthly_credit_limit=300, monthly_price_jpy=79800)
        repo.upsert_plan_by_code(code="growth", name="Growth", monthly_credit_limit=300, monthly_price_jpy=79800)
        repo.upsert_plan_by_code(code="growth", name="Growth", monthly_credit_limit=300, monthly_price_jpy=79800)

        matches = [p for p in repo.list_plans() if p.code == "growth"]
        assert len(matches) == 1

    def test_rerun_updates_changed_fields(self, repo):
        repo.upsert_plan_by_code(code="pro", name="Pro", monthly_credit_limit=650, monthly_price_jpy=149800)
        updated = repo.upsert_plan_by_code(code="pro", name="Pro", monthly_credit_limit=700, monthly_price_jpy=159800)

        assert updated.monthly_credit_limit == 700
        assert updated.monthly_price_jpy == 159800

    def test_full_replace_clears_fields_absent_from_new_definition(self, repo):
        """1回目はmarketing_note/価格ありで投入、2回目はそれらを省略(None)して
        再投入した場合、既存の値が残らずクリアされること（部分更新ではなく
        フル置換であることの確認）。"""
        repo.upsert_plan_by_code(
            code="pro-clear", name="Pro", monthly_credit_limit=650, monthly_price_jpy=149800,
            marketing_note="初期導入企業向けキャンペーン企画中",
        )
        updated = repo.upsert_plan_by_code(code="pro-clear", name="Pro", monthly_credit_limit=650)

        assert updated.monthly_price_jpy is None
        assert updated.marketing_note is None

    def test_does_not_reactivate_a_deactivated_plan(self, repo):
        """is_activeはseedの対象外: 一度is_active=falseにしたプランを
        再seedしても、意図せず復活しないこと。"""
        plan = repo.upsert_plan_by_code(code="legacy", name="Legacy", monthly_credit_limit=50)
        repo.update_plan(plan.id, is_active=False)

        reseeded = repo.upsert_plan_by_code(code="legacy", name="Legacy", monthly_credit_limit=50)
        assert reseeded.is_active is False

    def test_does_not_touch_active_plan_active_flag_either(self, repo):
        plan = repo.upsert_plan_by_code(code="active-plan", name="Active", monthly_credit_limit=50)
        assert plan.is_active is True
        reseeded = repo.upsert_plan_by_code(code="active-plan", name="Active", monthly_credit_limit=60)
        assert reseeded.is_active is True


class TestInitialSeedDataFile:
    """scripts/seed_data/pricing_plans.json （実運用で使われるマスタデータ本体）
    が期待する5プランを含み、そのまま複数回投入しても安全であることを確認する。
    CLI(seed-plans)のフィールド変換ロジックとは独立に、ファイル内容そのものを検証する。"""

    @pytest.fixture
    def seed_plan_defs(self):
        assert SEED_DATA_PATH.exists(), f"seed data file not found: {SEED_DATA_PATH}"
        with open(SEED_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data["plans"]

    def test_seed_file_defines_the_five_initial_plans(self, seed_plan_defs):
        codes = {p["code"] for p in seed_plan_defs}
        assert codes == {"monitor", "starter", "growth", "pro", "enterprise"}

    def test_monitor_and_enterprise_are_not_public(self, seed_plan_defs):
        by_code = {p["code"]: p for p in seed_plan_defs}
        assert by_code["monitor"]["is_public"] is False
        assert by_code["enterprise"]["is_public"] is False

    def test_starter_growth_pro_are_public_with_expected_credits(self, seed_plan_defs):
        by_code = {p["code"]: p for p in seed_plan_defs}
        assert by_code["starter"]["is_public"] is True
        assert by_code["starter"]["monthly_credit_limit"] == 100
        assert by_code["growth"]["is_public"] is True
        assert by_code["growth"]["monthly_credit_limit"] == 300
        assert by_code["pro"]["is_public"] is True
        assert by_code["pro"]["monthly_credit_limit"] == 650

    def test_pro_has_the_campaign_marketing_note(self, seed_plan_defs):
        by_code = {p["code"]: p for p in seed_plan_defs}
        assert by_code["pro"]["marketing_note"] == "初期導入企業向けキャンペーン企画中"

    def test_seeding_the_real_file_twice_is_idempotent(self, repo, seed_plan_defs):
        """実際のseedファイルの内容で2回投入しても5件のまま重複しないこと
        （CLIのseed-plansが最終的に呼ぶのと同じrepo層のAPIで検証）。"""
        for _ in range(2):
            for plan_def in seed_plan_defs:
                fields = {k: v for k, v in plan_def.items() if not k.startswith("_")}
                repo.upsert_plan_by_code(**fields)

        assert len(repo.list_plans()) == 5
        pro = repo.get_plan_by_code("pro")
        assert pro.monthly_credit_limit == 650
