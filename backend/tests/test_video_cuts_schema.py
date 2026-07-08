import pytest
from pydantic.v1 import ValidationError

from app.schemas.llm_response import (
    normalize_role_tag,
    VideoCutContent,
    VideoCutGenerationStatus,
    VideoSummary,
    VideoCutsBlock,
)
from app.schemas.ad_insight import AdInsightSpec, Diagnostics
from app.services.llm_validator_service import LLMValidatorService


class TestNormalizeRoleTag:
    """role_tag の内部語彙への正規化（新形式・旧データ自由記述の両方を吸収する）"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("hook", "hook"),
            ("Hook", "hook"),
            ("benefit", "benefit"),
            ("ベネフィット提示", "benefit"),
            ("proof", "proof"),
            ("証拠", "proof"),
            # 旧: 証拠と信頼を1カテゴリにまとめていた自由記述 → proof へ寄せる
            ("証拠・信頼形成", "proof"),
            ("trust", "trust"),
            ("信頼", "trust"),
            ("CTA", "cta"),
            ("cta", "cta"),
            ("unknown_free_text", "other"),
            (None, "other"),
            ("", "other"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_role_tag(raw) == expected

    def test_video_cut_content_normalizes_role_tag_on_construction(self):
        """VideoCutContent 生成時に role_tag が自動で内部語彙へ正規化される"""
        cut = VideoCutContent(
            cut_id="cut_1",
            role_tag="証拠・信頼形成",
            summary="画面内容の要約テキスト",
            improvement_suggestion="具体的な改善提案テキスト",
        )
        assert cut.role_tag == "proof"


class TestVideoCutContentOptionalFields:
    """strength_or_issue/evidence は段階1の必須表示に含まれないため optional"""

    def test_omitting_strength_or_issue_and_evidence_is_valid(self):
        cut = VideoCutContent(
            cut_id="cut_1",
            role_tag="hook",
            summary="画面内容の要約テキスト",
            improvement_suggestion="具体的な改善提案テキスト",
        )
        assert cut.strength_or_issue is None
        assert cut.evidence is None

    def test_start_end_seconds_default_to_none_until_orchestrator_merges_them(self):
        """start_seconds/end_secondsはバックエンド(VideoService.detect_cuts)側でマージされるため、
        LLM出力段階（cut_id/role_tag/summary/improvement_suggestionのみ）ではNoneのままでよい。"""
        cut = VideoCutContent(
            cut_id="cut_1",
            role_tag="hook",
            summary="画面内容の要約テキスト",
            improvement_suggestion="具体的な改善提案テキスト",
        )
        assert cut.start_seconds is None
        assert cut.end_seconds is None


class TestVideoCutGenerationStatus:
    """generation_status.status は success/failed/not_attempted の3値のみ許容する"""

    @pytest.mark.parametrize("status", ["success", "failed", "not_attempted"])
    def test_allowed_status_values(self, status):
        VideoCutGenerationStatus(status=status, error_code=None)

    def test_unknown_status_is_rejected(self):
        with pytest.raises(ValidationError):
            VideoCutGenerationStatus(status="bogus", error_code=None)


class TestVideoCutsBlockSchemaVersionBranching:
    """
    diagnostics.video_cuts は VideoCutsBlock（schema_version/generation_status/
    video_summary/video_cutsの4キー）で表現される。schema_version は将来の構造変更を
    区別するためのフィールドであり、v1.0時点ではこの1バージョンしか存在しないため
    分岐ロジック自体はまだ無いが、フィールドとして必ず出力される（VIDEO_CUTS_SCHEMA_VERSIONが
    default値として自動セットされる）ことをここで固定する。
    """

    def test_schema_version_defaults_to_1_0(self):
        block = VideoCutsBlock(
            generation_status=VideoCutGenerationStatus(status="not_attempted", error_code=None),
        )
        assert block.schema_version == "1.0"

    def test_success_shape(self):
        block = VideoCutsBlock(
            generation_status=VideoCutGenerationStatus(status="success", error_code=None),
            video_summary=VideoSummary(total_duration_seconds=15.9, cut_count=1),
            video_cuts=[
                VideoCutContent(
                    cut_id="cut_1",
                    start_seconds=0.0,
                    end_seconds=15.9,
                    role_tag="hook",
                    summary="画面内容の要約テキスト",
                    improvement_suggestion="具体的な改善提案テキスト",
                )
            ],
        )
        dumped = block.dict()
        assert dumped["generation_status"]["status"] == "success"
        assert dumped["video_summary"]["cut_count"] == 1
        assert len(dumped["video_cuts"]) == 1

    def test_failed_shape_has_no_video_summary(self):
        block = VideoCutsBlock(
            generation_status=VideoCutGenerationStatus(status="failed", error_code="TIME_BUDGET_EXCEEDED"),
        )
        assert block.video_summary is None
        assert block.video_cuts == []

    def test_not_attempted_shape_has_no_error_code(self):
        block = VideoCutsBlock(
            generation_status=VideoCutGenerationStatus(status="not_attempted", error_code=None),
        )
        assert block.generation_status.error_code is None
        assert block.video_summary is None


class TestDiagnosticsBackwardCompatibility:
    """
    diagnostics.video_cuts は Optional[VideoCutsBlock]。
    video_cuts自体を持たない旧レコード（本機能追加前に保存されたもの）でも
    Diagnostics構築自体は失敗しない（=書き込み側のモデルは後方互換）。

    なお、GET /specs/{asset_id} は保存済みspec_dataをこのモデルへ再検証せず
    生JSONのままレスポンスするため、旧形式（{"cuts": [...]}単体 + 別フィールドの
    video_cuts_error）で既に保存済みのレコードにこのテストは影響しない
    （フロントエンド側のシェイプ判定でカバーする領域であり、ここではモデル単体の
    後方互換性のみを検証する）。
    """

    def test_diagnostics_without_video_cuts_field_is_valid(self):
        diagnostics = Diagnostics(
            qualitative={
                "creative_fatigue_risk": "low",
                "creative_fatigue_basis": "テスト用の根拠テキストです",
            }
        )
        assert diagnostics.video_cuts is None


class TestValidateVideoCutsWithNormalization:
    """LLMValidatorService.validate_video_cuts はVideoCutContent経由でrole_tagを正規化する"""

    @pytest.fixture
    def validator(self):
        return LLMValidatorService()

    def test_free_text_role_tag_is_normalized_after_validation(self, validator):
        data = {
            "cuts": [
                {
                    "cut_id": "cut_1",
                    "role_tag": "証拠・信頼形成",
                    "summary": "画面内容の要約テキスト",
                    "improvement_suggestion": "具体的な改善提案テキスト",
                }
            ]
        }
        result = validator.validate_video_cuts(data, known_cut_ids=["cut_1"])
        assert result.cuts[0].role_tag == "proof"

    def test_missing_strength_or_issue_does_not_crash_abstract_word_check(self, validator):
        """strength_or_issueがoptional化された後も、抽象語チェックがNoneでクラッシュしないこと"""
        data = {
            "cuts": [
                {
                    "cut_id": "cut_1",
                    "role_tag": "hook",
                    "summary": "画面内容の要約テキスト",
                    "improvement_suggestion": "具体的な改善提案テキスト",
                }
            ]
        }
        result = validator.validate_video_cuts(data, known_cut_ids=["cut_1"])
        assert result.cuts[0].strength_or_issue is None
