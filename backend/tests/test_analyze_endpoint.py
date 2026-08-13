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
from app.models import MonitorCompany, MonitorUser
from app.api.deps import get_current_user
from app.api.routes import specs as specs_module
from app.services.meta_ads_csv_service import MetaAdsCsvError

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
def test_user(db_session):
    """招待制モニターベータ導入により /analyze 等はログイン必須になったため、
    テスト用の会社・ユーザーを1件用意し、get_current_user を差し替える。
    monthly_credit_limit は十分大きくして、既存テストが上限に引っかからないようにする。"""
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
    app.include_router(specs_module.router)

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


class TestMetaAdsCsvErrorHandling:
    """
    Meta Ads CSV取り込みで解析不能な場合、specs.py::analyze() が
    MetaAdsCsvError を汎用の500(ANALYSIS_ERROR)にせず、422 + 具体的な
    案内文(error_code="META_ADS_CSV_..."）として返すことの回帰テスト。

    実際のCSV解析ロジック自体は test_meta_ads_csv_service.py で検証済みのため、
    ここでは AnalysisOrchestrator.run() が MetaAdsCsvError を送出した場合の
    API層のハンドリングのみを検証する。
    """

    def test_meta_ads_csv_error_returns_422_with_guidance(self, client):
        csv_error = MetaAdsCsvError(
            "CSVから主要指標を読み取れませんでした（不足している列: インプレッション、クリック（すべて）"
            "）。Meta Ads Manager のエクスポート設定で、これらの指標を含めたうえで再度CSVを書き出し、"
            "そのままアップロードし直してください。",
            error_code="META_ADS_CSV_MISSING_REQUIRED_COLUMNS",
            missing_fields=["impressions", "clicks"],
        )

        with patch.object(specs_module.AnalysisOrchestrator, "run", side_effect=csv_error):
            response = client.post(
                "/api/v1/specs/analyze",
                files={
                    "input_file": ("test.png", b"fake-image-bytes", "image/png"),
                    "kpi_file": ("kpi.csv", b"campaign,spend\ntest,1000\n", "text/csv"),
                },
                data={"mode": "file_plus_lp_plus_manual_kpi"},
            )

        assert response.status_code == 422
        # このテスト用アプリは specs.router のみをマウントしており、main.py の
        # StarletteHTTPException用カスタムハンドラ（detailをトップレベルへ展開する）を
        # 経由しないため、FastAPIのデフォルト挙動どおり detail の下に入る。
        detail = response.json()["detail"]
        assert detail["error_code"] == "META_ADS_CSV_MISSING_REQUIRED_COLUMNS"
        assert "インプレッション" in detail["error"]
        assert detail["details"]["missing_fields"] == ["impressions", "clicks"]

    def test_meta_ads_csv_error_does_not_fall_through_to_generic_500(self, client):
        """MetaAdsCsvErrorがgenericなException分岐(500/ANALYSIS_ERROR)に落ちないこと"""
        csv_error = MetaAdsCsvError("CSVファイルが空です。", error_code="META_ADS_CSV_EMPTY")

        with patch.object(specs_module.AnalysisOrchestrator, "run", side_effect=csv_error):
            response = _post_analyze(client)

        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] != "ANALYSIS_ERROR"


class TestLpUrlInput:
    """
    主入力の再定義（docs/plans/primary_input_redesign.md）で追加した lp_url
    フォームパラメータ。LP を「URL文字列」として直接渡せること、lp_file との
    併用時は lp_url を優先すること、不正なURL形式は422で弾かれることを検証する。

    テストで使う lp_url には実在ドメイン（example.com等）ではなく、リテラルの
    パブリックIPアドレス（93.184.216.34）を使う。specs.py側のSSRF対策
    （_is_unsafe_lp_host）がホスト名解決にsocket.getaddrinfo()を使うため、
    ホスト名を渡すとテスト実行時に実際のDNS解決が発生してしまう
    （ネットワーク遮断環境でのテストの不安定化を避けるため、リテラルIPなら
    DNS解決自体が発生しない）。SSRF対策自体の専用テストは
    TestLpUrlSsrfProtection を参照。
    """

    def _spec_dict(self):
        d = _minimal_valid_spec_dict(asset_id="asset_lp_url_test")
        d["input_metadata"]["mode"] = "file_plus_lp"
        d["_metadata"]["input_mode"] = "file_plus_lp"
        d["landing_page"] = {"url": "https://93.184.216.34/lp"}
        return d

    def test_lp_url_is_passed_to_orchestrator_as_lp_input(self, client):
        spec_dict = self._spec_dict()
        with patch.object(specs_module, "AnalysisOrchestrator") as mock_orchestrator_cls:
            mock_orchestrator_cls.return_value.run.return_value = spec_dict
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "file_plus_lp", "lp_url": "https://93.184.216.34/lp"},
            )

        assert response.status_code == 200
        assert mock_orchestrator_cls.call_args.kwargs["lp_input"] == "https://93.184.216.34/lp"

    def test_lp_url_takes_precedence_over_lp_file(self, client):
        """lp_url と lp_file が両方指定された場合、lp_url を優先しファイル保存自体を行わないこと"""
        spec_dict = self._spec_dict()
        with patch.object(specs_module, "AnalysisOrchestrator") as mock_orchestrator_cls:
            mock_orchestrator_cls.return_value.run.return_value = spec_dict
            response = client.post(
                "/api/v1/specs/analyze",
                files={
                    "input_file": ("test.png", b"fake-image-bytes", "image/png"),
                    "lp_file": ("lp.html", b"<html></html>", "text/html"),
                },
                data={"mode": "file_plus_lp", "lp_url": "https://93.184.216.34/lp"},
            )

        assert response.status_code == 200
        assert mock_orchestrator_cls.call_args.kwargs["lp_input"] == "https://93.184.216.34/lp"

    def test_invalid_lp_url_scheme_returns_422(self, client):
        response = client.post(
            "/api/v1/specs/analyze",
            files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
            data={"mode": "file_plus_lp", "lp_url": "example.com/lp"},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "VALIDATION_ERROR"


class TestLpUrlSsrfProtection:
    """
    lp_url がサーバー側（LPService）からのHTTP GET対象になることを踏まえた
    SSRF対策（specs.py::_is_unsafe_lp_host）の回帰テスト。PR #93レビューで
    指摘された、認証済みユーザーが内部アドレス/クラウドメタデータエンドポイントを
    lp_url経由で到達させられる問題への対応。

    すべてリテラルIPアドレス/既知の禁止ホスト名を使い、実際のDNS解決や
    ネットワークI/Oを発生させない。
    """

    @pytest.mark.parametrize(
        "lp_url",
        [
            "http://127.0.0.1/",  # loopback
            "http://localhost/",  # 明示的に禁止したホスト名
            "http://169.254.169.254/computeMetadata/v1/",  # link-local / GCPメタデータ
            "http://metadata.google.internal/computeMetadata/v1/",  # GCPメタデータのホスト名
            "http://10.0.0.5/",  # RFC1918 private
            "http://172.16.0.5/",  # RFC1918 private
            "http://192.168.1.5/",  # RFC1918 private
            "http://[::1]/",  # IPv6 loopback
        ],
    )
    def test_unsafe_lp_url_host_is_rejected(self, client, lp_url):
        response = client.post(
            "/api/v1/specs/analyze",
            files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
            data={"mode": "file_plus_lp", "lp_url": lp_url},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "VALIDATION_ERROR"

    def test_safe_public_lp_url_is_accepted(self, client):
        """パブリックIPを指した通常のlp_urlは、SSRF対策の追加後も引き続き利用できること"""
        spec_dict = _minimal_valid_spec_dict(asset_id="asset_lp_url_safe_test")
        spec_dict["input_metadata"]["mode"] = "file_plus_lp"
        spec_dict["_metadata"]["input_mode"] = "file_plus_lp"
        spec_dict["landing_page"] = {"url": "https://93.184.216.34/lp"}

        with patch.object(specs_module, "AnalysisOrchestrator") as mock_orchestrator_cls:
            mock_orchestrator_cls.return_value.run.return_value = spec_dict
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "file_plus_lp", "lp_url": "https://93.184.216.34/lp"},
            )

        assert response.status_code == 200

    def test_unresolvable_hostname_is_not_blocked_here(self, client):
        """
        名前解決できないホストは、この時点では拒否しない（安全側ではあるが誤検知回避を
        優先する設計。_is_unsafe_lp_host()のdocstring参照）。実際のfetchは後続の
        LPServiceが行い、そこで失敗する。ここではspecs.pyの422バリデーションを
        通過することだけを確認する（Orchestrator自体はモックするため実fetchは発生しない）。

        socket.getaddrinfo自体をモックしてgaierrorを起こし、テスト実行環境の実際の
        DNS解決可否（ネットワーク遮断環境での失敗・遅延）に依存しないようにする。
        """
        spec_dict = _minimal_valid_spec_dict(asset_id="asset_lp_url_unresolvable_test")
        spec_dict["input_metadata"]["mode"] = "file_plus_lp"
        spec_dict["_metadata"]["input_mode"] = "file_plus_lp"
        spec_dict["landing_page"] = {"url": "https://this-host-should-not-resolve.invalid/lp"}

        with patch.object(specs_module, "AnalysisOrchestrator") as mock_orchestrator_cls, \
                patch.object(specs_module.socket, "getaddrinfo", side_effect=specs_module.socket.gaierror):
            mock_orchestrator_cls.return_value.run.return_value = spec_dict
            response = client.post(
                "/api/v1/specs/analyze",
                files={"input_file": ("test.png", b"fake-image-bytes", "image/png")},
                data={"mode": "file_plus_lp", "lp_url": "https://this-host-should-not-resolve.invalid/lp"},
            )

        assert response.status_code == 200


class TestFilePlusKpiMode:
    """
    主入力の再定義で追加した file_plus_kpi モード（クリエイティブ + KPI、LPなし・
    広告面分析）が、/analyze エンドポイントで受理されエンドツーエンドで動作することの
    回帰テスト。スキーマレベルの詳細な検証は test_input_mode_schema.py を参照。
    """

    def test_file_plus_kpi_mode_is_accepted(self, client):
        spec_dict = _minimal_valid_spec_dict(asset_id="asset_file_plus_kpi_test")
        spec_dict["input_metadata"]["mode"] = "file_plus_kpi"
        spec_dict["_metadata"]["input_mode"] = "file_plus_kpi"
        spec_dict["performance"] = {"impressions": 1000, "clicks": 10}

        with patch.object(specs_module.AnalysisOrchestrator, "run", return_value=spec_dict):
            response = client.post(
                "/api/v1/specs/analyze",
                files={
                    "input_file": ("test.png", b"fake-image-bytes", "image/png"),
                    "kpi_file": ("kpi.csv", b"impressions,clicks\n1000,10\n", "text/csv"),
                },
                data={"mode": "file_plus_kpi"},
            )

        assert response.status_code == 200
        assert response.json()["performance"]["impressions"] == 1000
        assert response.json()["landing_page"] is None
