"""
POST /api/v1/specs/analyze エンドポイントのテスト（Phase 2 P1 follow-up）。

AnalysisOrchestrator.run()（実I/Oを伴う重い処理）をモックし、specs.py::analyze()
自体の配線ロジック（DB保存はspec_dataのみ／asset_data・evaluation_dataは
レスポンスにのみ含める／decision_support_diffが両方のdiagnostics表現で
一致すること）を検証する。

このリポジトリにこれまでTestClientベースのエンドポイントテストは無かったため、
specs.routerだけをマウントした最小のFastAPIアプリ + インメモリSQLiteで検証する
（test_repositories.pyのDBセットアップパターンを踏襲）。
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models.ad_insight import AdInsight
from app.api.routes import specs as specs_module

# StaticPool: sqlite:///:memory: は接続ごとに別DBになるため、TestClient経由の
# リクエスト（別スレッド/別チェックアウトで接続を取得しうる）でも同じDBを
# 見るよう、単一コネクションを強制する（test_repositories.pyの単一session内
# 完結パターンと異なり、ここではHTTPリクエストを挟むため必要）。
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
    app = FastAPI()
    app.include_router(specs_module.router)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _minimal_valid_spec_dict(asset_id="asset_endpoint_test_0001"):
    """AdInsightSpec(**spec_dict) をそのまま通る最小構成（file_onlyモード）"""
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


def _post_analyze(client, filename="test.png", content=b"fake-image-bytes"):
    return client.post(
        "/api/v1/specs/analyze",
        files={"input_file": (filename, content, "image/png")},
        data={"mode": "file_only"},
    )


class TestAssetEvaluationDataInResponse:
    """Fix 5: /analyze のレスポンスに asset_data/evaluation_data が含まれること。
    DB保存はspec_dataのみで変更していないことも合わせて確認する。"""

    def test_response_includes_asset_data_and_evaluation_data(self, client):
        spec_dict = _minimal_valid_spec_dict()
        spec_dict["asset_data"] = {"asset_meta": {"asset_id": spec_dict["asset_meta"]["asset_id"]}, "sentinel": "asset"}
        spec_dict["evaluation_data"] = {
            "evaluation_meta": {"evaluator_model": "gpt-4o"},
            "diagnostics": {"qualitative": {"creative_fatigue_risk": "low"}},
            "sentinel": "evaluation",
        }

        with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict):
            response = _post_analyze(client)

        assert response.status_code == 200
        body = response.json()
        assert body["asset_data"]["sentinel"] == "asset"
        assert body["evaluation_data"]["sentinel"] == "evaluation"

    def test_db_record_spec_data_does_not_contain_asset_or_evaluation_data(self, client, db_session):
        """DB保存挙動は変更していないことの確認（dual-writeなし）"""
        spec_dict = _minimal_valid_spec_dict(asset_id="asset_endpoint_test_0002")
        spec_dict["asset_data"] = {"sentinel": "asset"}
        spec_dict["evaluation_data"] = {"sentinel": "evaluation"}

        with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict):
            response = _post_analyze(client)

        assert response.status_code == 200
        record = db_session.query(AdInsight).filter(
            AdInsight.asset_id == "asset_endpoint_test_0002"
        ).one()
        assert "asset_data" not in record.spec_data
        assert "evaluation_data" not in record.spec_data
        # カラム自体もdual-writeしていないためNULLのまま
        assert record.asset_data is None
        assert record.evaluation_data is None

    def test_response_still_works_when_generation_failed_upstream(self, client):
        """ConverterServiceでのfail-softによりasset_data/evaluation_dataがNoneでも
        レスポンス自体は成功すること"""
        spec_dict = _minimal_valid_spec_dict(asset_id="asset_endpoint_test_0003")
        spec_dict["asset_data"] = None
        spec_dict["evaluation_data"] = None

        with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict):
            response = _post_analyze(client)

        assert response.status_code == 200
        body = response.json()
        assert body["asset_data"] is None
        assert body["evaluation_data"] is None


class TestDecisionSupportDiffConsistency:
    """Fix 1: decision_support_diff が response['diagnostics'] と
    response['evaluation_data']['diagnostics'] の両方に一致して現れること"""

    def test_diff_appears_identically_in_both_diagnostics_representations(self, client, db_session):
        asset_id = "asset_endpoint_test_0004"
        # 前バージョンを直接DBへ用意しておく（get_previous_versionがヒットする状態を作る）
        db_session.add(AdInsight(asset_id=asset_id, version=1, format="image_static", spec_data={"diagnostics": {}}))
        db_session.commit()

        spec_dict = _minimal_valid_spec_dict(asset_id=asset_id)
        spec_dict["evaluation_data"] = {
            "evaluation_meta": {"evaluator_model": "gpt-4o"},
            # decision_support_diff注入前のevaluation_data.diagnostics
            # （ConverterServiceが実際に生成する時点の内容を模している）
            "diagnostics": {"qualitative": {"creative_fatigue_risk": "low"}},
        }
        spec_dict["asset_data"] = None

        fake_diff = {"previous_version": 1, "overall_rank_delta": 1, "axis_deltas": []}

        with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict), \
             patch.object(specs_module, "_build_decision_support_diff", return_value=fake_diff):
            response = _post_analyze(client)

        assert response.status_code == 200
        body = response.json()
        assert body["diagnostics"]["decision_support_diff"] == fake_diff
        assert body["evaluation_data"]["diagnostics"]["decision_support_diff"] == fake_diff

    def test_no_diff_key_when_no_previous_version_exists(self, client):
        """前バージョンが存在しない通常ケースでは、decision_support_diffキー自体が
        両方の diagnostics に現れないこと（回帰確認）"""
        spec_dict = _minimal_valid_spec_dict(asset_id="asset_endpoint_test_0005")
        spec_dict["evaluation_data"] = {
            "evaluation_meta": {"evaluator_model": "gpt-4o"},
            "diagnostics": {"qualitative": {"creative_fatigue_risk": "low"}},
        }
        spec_dict["asset_data"] = None

        with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict):
            response = _post_analyze(client)

        assert response.status_code == 200
        body = response.json()
        assert "decision_support_diff" not in body["diagnostics"]
        assert "decision_support_diff" not in body["evaluation_data"]["diagnostics"]
