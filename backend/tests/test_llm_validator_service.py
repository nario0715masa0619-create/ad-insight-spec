import pytest
from app.services.llm_validator_service import LLMValidatorService
from app.schemas.llm_response import ImprovementCommentsSchema, LLMImprovementValidationError

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
