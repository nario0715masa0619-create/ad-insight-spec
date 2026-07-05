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
    """decision_support（強み・弱み・改善提案）バリデーションテスト"""

    @pytest.fixture
    def validator(self):
        return LLMValidatorService()

    @pytest.fixture
    def valid_data(self):
        return {
            "summary": {
                "headline": "LPとの連動は強いが、動画冒頭のフックが弱くCTRで機会損失",
                "decision": "改修推奨",
                "rationale": "LP整合性は高いが、フックの抽象さが視聴維持率を下げている",
            },
            "strengths": [
                {
                    "id": "s1",
                    "category": "lp",
                    "title": "LPとの完全一致",
                    "description": "広告文とLPのFVコピーが『成約率2倍』で完全一致している",
                    "keep_reason": "信頼感とCVRに直結するため今後も維持すべき",
                }
            ],
            "weaknesses": [
                {
                    "id": "w1",
                    "priority": "P1",
                    "category": "message",
                    "title": "冒頭フックの抽象さ",
                    "description": "動画冒頭3秒のテキストが抽象的で視聴維持につながっていない",
                    "impact": "視聴完了率とCTRの両方を下げている",
                }
            ],
            "recommendations": [
                {
                    "id": "r1",
                    "priority": "P1",
                    "target_weakness_ids": ["w1"],
                    "title": "冒頭ペインポイント訴求への変更",
                    "what": "動画0-3秒にペインポイント訴求のテキストを配置する",
                    "why": "弱み『冒頭フックの抽象さ』を解消するため",
                    "how": "既存クリエイティブとABテストしCTRを比較する",
                    "expected_effect": "CTR改善を見込む",
                }
            ],
        }

    def test_valid_decision_support(self, validator, valid_data):
        """正常な decision_support はそのまま検証を通過する"""
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, DecisionSupport)
        assert result.strengths[0].id == "s1"
        assert result.weaknesses[0].id == "w1"
        assert result.recommendations[0].target_weakness_ids == ["w1"]

    def test_missing_required_field(self, validator, valid_data):
        """summary/strengths/weaknesses/recommendations のいずれか欠落は失敗"""
        del valid_data["weaknesses"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "MISSING_FIELD"

    def test_unknown_target_weakness_id_rejected(self, validator, valid_data):
        """recommendation が実在しない weakness id を参照している場合は失敗"""
        valid_data["recommendations"][0]["target_weakness_ids"] = ["w999"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert "w999" in result.reason

    def test_abstract_word_in_weakness_rejected(self, validator, valid_data):
        """weakness の本文に抽象語が含まれる場合は失敗"""
        valid_data["weaknesses"][0]["title"] = "訴求力が弱い"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_abstract_word_in_strength_rejected(self, validator, valid_data):
        """strength の本文に抽象語が含まれる場合は失敗"""
        valid_data["strengths"][0]["description"] = "全体的に魅力があるビジュアル"
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_empty_arrays_do_not_crash(self, validator, valid_data):
        """strengths/weaknesses/recommendations が空でもクラッシュせず成功として扱う"""
        empty_data = {
            "summary": valid_data["summary"],
            "strengths": [],
            "weaknesses": [],
            "recommendations": [],
        }
        result = validator.validate_decision_support(empty_data)
        assert isinstance(result, DecisionSupport)
        assert result.strengths == []
        assert result.weaknesses == []
        assert result.recommendations == []

    def test_recommendation_missing_why_rejected(self, validator, valid_data):
        """recommendation に why が欠落している場合は失敗（What/Why/How必須）"""
        del valid_data["recommendations"][0]["why"]
        result = validator.validate_decision_support(valid_data)
        assert isinstance(result, LLMDecisionSupportValidationError)

    def test_non_dict_input_rejected(self, validator):
        """dict以外の入力は INVALID_STRUCTURE で失敗"""
        result = validator.validate_decision_support(["not", "a", "dict"])
        assert isinstance(result, LLMDecisionSupportValidationError)
        assert result.error_code == "INVALID_STRUCTURE"
