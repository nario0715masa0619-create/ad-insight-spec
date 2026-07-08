import pytest
from app.services.llm_validator_service import LLMValidatorService
from app.schemas.llm_response import (
    ImprovementCommentsSchema,
    LLMImprovementValidationError,
    DecisionSupport,
    LLMDecisionSupportValidationError,
)

class TestLLMValidatorService:
    """改善コメント品質検証テスト（5観点）"""
    
    @pytest.fixture
    def validator(self):
        return LLMValidatorService()
    
    # ===== 観点 1: 構造化コメント生成成功 =====
    def test_valid_improvement_comment_generation(self, validator):
        """正常な改善コメント生成"""
        data = {
            "comments": [
                {
                    "issue_summary": "CTA ボタンのテキストが曖昧",
                    "target_scope": "Call-to-Action ボタン",
                    "evidence": "ボタンテキストが『詳細を見る』で、行動を促す動詞がない",
                    "recommended_action": "『今すぐ登録』に変更",
                    "priority": "P1",
                    "expected_impact": "クリック率 5～10% 向上",
                    "confidence": 0.85
                }
            ],
            "total_count": 1,
            "summary": "CTA 訴求力向上が必須"
        }
        
        result = validator.validate_improvement_comments(data)
        
        assert isinstance(result, ImprovementCommentsSchema)
        assert len(result.comments) == 1
        assert result.comments[0].issue_summary == "CTA ボタンのテキストが曖昧"
    
    # ===== 観点 2: 根拠欠落検知 =====
    def test_missing_evidence_detection(self, validator):
        """根拠なし検知"""
        data = {
            "comments": [
                {
                    "issue_summary": "CTA が弱い",
                    "target_scope": "CTA",
                    "evidence": "短い",  # 10 文字未満 → NG
                    "recommended_action": "変更する",
                    "priority": "P1",
                    "expected_impact": "向上",
                    "confidence": 0.8
                }
            ],
            "total_count": 1,
            "summary": ""
        }
        
        result = validator.validate_improvement_comments(data)
        
        assert isinstance(result, LLMImprovementValidationError)
        assert result.success is False
        assert "evidence" in result.reason or "short" in result.reason
    
    # ===== 観点 3: 対象不明検知 =====
    def test_vague_target_scope_detection(self, validator):
        """対象箇所不明検知"""
        data = {
            "comments": [
                {
                    "issue_summary": "改善が必要",
                    "target_scope": "広告",  # あまりに曖昧
                    "evidence": "視認性が低い傾向があるため変更すべき",
                    "recommended_action": "デザインを変更する",
                    "priority": "P2",
                    "expected_impact": "改善される",
                    "confidence": 0.7
                }
            ],
            "total_count": 1,
            "summary": ""
        }
        
        result = validator.validate_improvement_comments(data)
        
        assert isinstance(result, LLMImprovementValidationError)
        assert result.success is False
        assert "target_scope" in result.reason or "vague" in result.reason
    
    # ===== 観点 4: 抽象語過多検知 =====
    def test_abstract_words_detection(self, validator):
        """抽象語過多検知"""
        data = {
            "comments": [
                {
                    "issue_summary": "訴求力と魅力に改善余地がある",  # 抽象語が複数
                    "target_scope": "クリエイティブ全体",
                    "evidence": "クリックが少ない傾向があるため",
                    "recommended_action": "インパクトを強く変更する",  # 抽象語
                    "priority": "P0",
                    "expected_impact": "効果が出る",
                    "confidence": 0.9
                }
            ],
            "total_count": 1,
            "summary": ""
        }
        
        result = validator.validate_improvement_comments(data)
        
        assert isinstance(result, LLMImprovementValidationError)
        assert result.success is False
        assert "abstract" in result.reason
    
    # ===== 観点 5: 矛盾検知 & fail-soft =====
    def test_contradictory_statements_detection(self, validator):
        """矛盾表現検知"""
        data = {
            "comments": [
                {
                    "issue_summary": "見出しが明確だが不明確という評価を受けている",  # 矛盾
                    "target_scope": "見出し",
                    "evidence": "複数の解釈が可能な表現になっている",
                    "recommended_action": "単一の意味に限定する表現に変更",
                    "priority": "P1",
                    "expected_impact": "メッセージの明確化",
                    "confidence": 0.8
                }
            ],
            "total_count": 1,
            "summary": ""
        }
        
        result = validator.validate_improvement_comments(data)
        
        assert isinstance(result, LLMImprovementValidationError)
        assert result.success is False
        assert "contradiction" in result.reason or "contradictory" in result.reason
    
    # ===== ボーナステスト: fail-soft の返却形式確認 =====
    def test_fail_soft_response_structure(self, validator):
        """fail-soft 時の構造化エラー返却"""
        data = {
            "comments": []  # 空リスト → バリデーションは通る
        }
        
        result = validator.validate_improvement_comments(data)
        
        # 空リストは OK（コメントなし = 改善なし）
        assert isinstance(result, ImprovementCommentsSchema)
        assert len(result.comments) == 0
    
    def test_fail_soft_error_structure(self, validator):
        """エラー時のレスポンス構造確認"""
        data = {
            "comments": [
                {
                    "issue_summary": "問題がある",
                    "target_scope": "X",  # 短すぎる
                    "evidence": "短",  # 短すぎる
                    "recommended_action": "?",  # 不十分
                    "priority": "P0",
                    "expected_impact": "OK",
                    "confidence": 0.5
                }
            ],
            "total_count": 1,
            "summary": ""
        }
        
        result = validator.validate_improvement_comments(data)

        # fail-soft: エラーを構造化して返す
        assert isinstance(result, LLMImprovementValidationError)
        assert result.success is False
        assert result.error_code in [
            "COMMENT_VALIDATION_FAILED",
            "INVALID_STRUCTURE"
        ]
        assert len(result.reason) > 0


class TestDecisionSupportValidation:
    """decision_support（5軸 × 強み・弱み・改善提案）バリデーションテスト"""

    @pytest.fixture
    def validator(self):
        return LLMValidatorService()

    @staticmethod
    def _make_axis(axis_id: str, axis_label: str = "軸"):
        return {
            "axis": axis_id,
            "axis_label": axis_label,
            "score": 3,
            "strength": {
                "target_element": "ファーストビューのテキスト",
                "aspect": "数字訴求の具体性",
                "description": "広告文とLPのFVコピーが『成約率2倍』で完全一致している",
                "reason": "具体的な数字による訴求は信頼されやすいため",
                "keep_reason": "信頼感とCVRに直結するため今後も維持すべき",
                "evidence": {
                    "location": "ファーストビューのテキスト『成約率2倍』",
                    "viewpoint": "訴求軸",
                    "evaluation": "具体的な数字訴求で説得力が高い",
                    "rationale": "OCRテキストと構図から数字訴求の一致を確認",
                },
            },
            "weakness": {
                "target_element": "動画冒頭0〜3秒のテキスト",
                "aspect": "冒頭フックの具体性",
                "description": "動画冒頭3秒のテキストが抽象的で視聴維持につながっていない",
                "reason": "冒頭3秒で具体的なペインポイントを提示しないと離脱が増えるため",
                "impact": "視聴完了率とCTRの両方を下げている",
                "evidence": {
                    "location": "動画0〜3秒目",
                    "viewpoint": "訴求軸",
                    "evaluation": "ペインポイントへの言及が無く抽象的",
                    "rationale": "トーン情報の訴求軸がイメージ訴求のみであることを確認",
                },
            },
            "recommendation": {
                "what": "動画0-3秒にペインポイント訴求のテキストを配置する",
                "why": "弱み『冒頭フックの抽象さ』を解消するため",
                "how": "既存クリエイティブとABテストしCTRを比較する",
                "expected_effect": "CTR改善を見込む",
            },
        }

    @pytest.fixture
    def valid_data(self):
        return {
            "summary": {
                "headline": "LPとの連動は強いが、動画冒頭のフックが弱くCTRで機会損失",
                "decision": "改修推奨",
                "rationale": "LP整合性は高いが、フックの抽象さが視聴維持率を下げている",
            },
            "axes": [
                self._make_axis("appeal", "訴求軸"),
                self._make_axis("creative", "クリエイティブ"),
                self._make_axis("cta", "CTA"),
                self._make_axis("trust", "信頼"),
                self._make_axis("target", "ターゲット"),
            ],
        }

    def test_valid_decision_support(self, validator, valid_data):
        """正常な decision_support はそのまま検証を通過する（5軸すべて存在）"""
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, DecisionSupport)
        assert len(result.axes) == 5
        assert [a.axis for a in result.axes] == ["appeal", "creative", "cta", "trust", "target"]

    def test_distinct_aspect_passes(self, validator, valid_data):
        """strength.aspect と weakness.aspect が異なる観点であれば通過する"""
        valid_data["axes"][0]["strength"]["aspect"] = "数字訴求の具体性"
        valid_data["axes"][0]["weakness"]["aspect"] = "冒頭フックの具体性"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, DecisionSupport)

    def test_same_aspect_in_strength_and_weakness_rejected(self, validator, valid_data):
        """同一軸でstrength.aspectとweakness.aspectが完全一致する場合は矛盾として失敗する
        （例: 信頼軸で『信頼性が強み』『信頼性が弱み』のような両論併記を防ぐ）"""
        valid_data["axes"][0]["strength"]["aspect"] = "信頼性"
        valid_data["axes"][0]["weakness"]["aspect"] = "信頼性"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "ITEM_VALIDATION_FAILED"
        assert "aspect" in result.reason

    def test_missing_required_field(self, validator, valid_data):
        """summary/axes のいずれか欠落は失敗"""
        del valid_data["axes"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "MISSING_FIELD"

    def test_missing_axis_rejected(self, validator, valid_data):
        """5軸のいずれかが欠落している場合は失敗"""
        valid_data["axes"] = valid_data["axes"][:4]  # target 軸を欠落させる
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "AXIS_COVERAGE_INVALID"
        assert "target" in result.reason

    def test_duplicate_axis_rejected(self, validator, valid_data):
        """同じ軸が重複している場合は失敗"""
        valid_data["axes"][4]["axis"] = "appeal"  # target の代わりに appeal を重複させる
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "AXIS_COVERAGE_INVALID"

    def test_unknown_axis_rejected(self, validator, valid_data):
        """未知の軸IDは失敗"""
        valid_data["axes"][0]["axis"] = "unknown_axis"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "AXIS_COVERAGE_INVALID"

    def test_abstract_word_in_weakness_rejected(self, validator, valid_data):
        """weakness の本文に抽象語が含まれる場合は失敗"""
        valid_data["axes"][0]["weakness"]["description"] = "訴求力が弱い説明文です"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_abstract_word_in_strength_rejected(self, validator, valid_data):
        """strength の本文に抽象語が含まれる場合は失敗"""
        valid_data["axes"][0]["strength"]["description"] = "全体的に魅力があるビジュアルです"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_recommendation_missing_expected_effect_rejected(self, validator, valid_data):
        """recommendation に expected_effect が欠落している場合は失敗（What/Why/How/期待効果必須）"""
        del valid_data["axes"][0]["recommendation"]["expected_effect"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_expected_effect_without_metric_keyword_rejected(self, validator, valid_data):
        """expected_effect が具体的な指標語を含まない場合は失敗"""
        valid_data["axes"][0]["recommendation"]["expected_effect"] = "効果が期待できると考えられる"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert "expected_effect" in result.reason

    def test_missing_evidence_field_rejected(self, validator, valid_data):
        """evidence の4点セット（location/viewpoint/evaluation/rationale）のいずれか欠落は失敗"""
        del valid_data["axes"][0]["strength"]["evidence"]["rationale"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_missing_target_element_rejected(self, validator, valid_data):
        """target_element（対象要素の特定）が欠落している場合は失敗"""
        del valid_data["axes"][0]["weakness"]["target_element"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_non_dict_input_rejected(self, validator):
        """dict以外の入力は INVALID_STRUCTURE で失敗"""
        result = validator.validate_decision_support(["not", "a", "dict"])
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "INVALID_STRUCTURE"
