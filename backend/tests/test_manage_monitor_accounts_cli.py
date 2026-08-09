"""
scripts/manage_monitor_accounts.py (CLIラッパー本体) の軽量テスト。

これまでこのスクリプトの動作確認は手動実行のみで、内部の MonitorRepository
メソッド自体は他のテストで担保されていても、CLI側の配線（引数の受け渡し、
seed-plans の dry-run 分岐、JSONからのフィールド抽出、limit_source表示の
呼び出し経路）は自動テストの対象外だった（レビュー指摘: CLI自動テスト不足）。

scripts/ 配下は独立したパッケージではないため、sys.path 経由で直接
import する。DBはCLIモジュールが束縛している SessionLocal/engine を
monkeypatch でインメモリSQLiteに差し替えることで、実ファイル
（開発者のローカルDB等）に一切触れずに検証する。
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import manage_monitor_accounts as cli  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.models import PricingPlan  # noqa: E402


@pytest.fixture
def cli_db(monkeypatch):
    """CLIモジュールが参照する SessionLocal/engine を、隔離されたインメモリ
    SQLiteに差し替える。開発者の実DBファイルには一切書き込まない。
    テーブルはここで前もって作成しておく（cmd_*関数もBase.metadata.create_all
    を呼ぶが、テスト側で先にDBへ直接書き込むケースに備えて明示しておく）。"""
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(cli, "engine", test_engine)
    monkeypatch.setattr(cli, "SessionLocal", TestingSessionLocal)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)


def _read_plan_codes(cli_db):
    session = sessionmaker(bind=cli_db)()
    try:
        return {p.code for p in session.query(PricingPlan).all()}
    finally:
        session.close()


class TestSeedPlansDryRun:
    def test_dry_run_writes_nothing(self, cli_db, capsys, tmp_path):
        seed_file = tmp_path / "plans.json"
        seed_file.write_text(
            json.dumps({"plans": [{"code": "dry-plan", "name": "Dry", "monthly_credit_limit": 10}]}),
            encoding="utf-8",
        )
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=True))

        assert _read_plan_codes(cli_db) == set()
        assert "[dry-run]" in capsys.readouterr().out

    def test_dry_run_reports_create_vs_update(self, cli_db, capsys, tmp_path):
        seed_file = tmp_path / "plans.json"
        seed_file.write_text(
            json.dumps({"plans": [{"code": "existing-plan", "name": "V1", "monthly_credit_limit": 10}]}),
            encoding="utf-8",
        )
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))
        capsys.readouterr()  # 1回目の出力は捨てる

        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=True))
        out = capsys.readouterr().out
        assert "would update plan 'existing-plan'" in out


class TestSeedPlansRealRun:
    def test_seed_creates_all_plans_from_file(self, cli_db, tmp_path):
        seed_file = tmp_path / "plans.json"
        seed_file.write_text(
            json.dumps(
                {
                    "plans": [
                        {"code": "a-plan", "name": "A", "monthly_credit_limit": 1},
                        {"code": "b-plan", "name": "B", "monthly_credit_limit": 2},
                    ]
                }
            ),
            encoding="utf-8",
        )
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))
        assert _read_plan_codes(cli_db) == {"a-plan", "b-plan"}

    def test_rerunning_seed_is_idempotent(self, cli_db, tmp_path):
        seed_file = tmp_path / "plans.json"
        seed_file.write_text(
            json.dumps({"plans": [{"code": "idempotent-plan", "name": "V1", "monthly_credit_limit": 5}]}),
            encoding="utf-8",
        )
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))

        session = sessionmaker(bind=cli_db)()
        try:
            matches = session.query(PricingPlan).filter(PricingPlan.code == "idempotent-plan").all()
            assert len(matches) == 1
        finally:
            session.close()

    def test_seed_does_not_touch_is_active_on_rerun(self, cli_db, tmp_path):
        seed_file = tmp_path / "plans.json"
        seed_file.write_text(
            json.dumps({"plans": [{"code": "deactivated-plan", "name": "V1", "monthly_credit_limit": 5}]}),
            encoding="utf-8",
        )
        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))

        session = sessionmaker(bind=cli_db)()
        try:
            plan = session.query(PricingPlan).filter(PricingPlan.code == "deactivated-plan").one()
            plan.is_active = False
            session.commit()
        finally:
            session.close()

        cli.cmd_seed_plans(SimpleNamespace(file=str(seed_file), dry_run=False))

        session = sessionmaker(bind=cli_db)()
        try:
            plan = session.query(PricingPlan).filter(PricingPlan.code == "deactivated-plan").one()
            assert plan.is_active is False
        finally:
            session.close()

    def test_seed_missing_file_exits_with_error(self, cli_db, capsys, tmp_path):
        missing_file = tmp_path / "does-not-exist.json"
        with pytest.raises(SystemExit):
            cli.cmd_seed_plans(SimpleNamespace(file=str(missing_file), dry_run=False))
        assert "not found" in capsys.readouterr().err


class TestCompanyLifecycleThroughCli:
    def test_create_company_with_zero_limit_and_list_usage_shows_override(self, cli_db, capsys):
        cli.cmd_create_company(
            SimpleNamespace(name="Zero Co", slug="zero-co-cli", limit=0, plan_code=None)
        )
        capsys.readouterr()

        cli.cmd_list_usage(SimpleNamespace())
        out = capsys.readouterr().out
        assert "zero-co-cli" in out
        assert "override" in out

    def test_create_company_with_plan_code_shows_plan_source(self, cli_db, capsys):
        seed_session = sessionmaker(bind=cli_db)()
        try:
            from app.repositories import MonitorRepository

            MonitorRepository(seed_session).create_plan(
                code="cli-plan", name="CLI Plan", monthly_credit_limit=42
            )
        finally:
            seed_session.close()

        cli.cmd_create_company(
            SimpleNamespace(name="Plan Co", slug="plan-co-cli", limit=None, plan_code="cli-plan")
        )
        capsys.readouterr()

        cli.cmd_list_usage(SimpleNamespace())
        out = capsys.readouterr().out
        assert "plan:cli-plan" in out

    def test_create_company_with_unknown_plan_code_exits_with_error(self, cli_db, capsys):
        with pytest.raises(SystemExit):
            cli.cmd_create_company(
                SimpleNamespace(name="Bad Co", slug="bad-co-cli", limit=None, plan_code="no-such-plan")
            )
        assert "not found" in capsys.readouterr().err


class TestParseIsoDatetime:
    def test_none_stays_none(self):
        assert cli._parse_iso_datetime(None) is None

    def test_parses_iso_string(self):
        parsed = cli._parse_iso_datetime("2026-09-01T00:00:00")
        assert parsed == datetime(2026, 9, 1, 0, 0, 0)
