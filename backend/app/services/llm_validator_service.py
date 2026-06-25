import re
from typing import Union, List, Dict, Any
from app.schemas.llm_response import ImprovementCommentsSchema, ImprovementComment, LLMImprovementValidationError
import logging

logger = logging.getLogger(__name__)

class LLMValidatorService:
    """改善コメント品質検証サービス"""
    
    # ===== 検知対象の抽象語 =====
    ABSTRACT_WORDS = [
        "改善余地",
        "訴求力",
        "魅力",
        "分かりやすさ",
        "インパクト",
        "工夫",
        "仕掛け",
        "チカラ",
        "違和感"
    ]
    
    # ===== 矛盾検知の相反表現 =====
    CONTRADICTORY_PAIRS = [
        ("明確", "不明確"),
        ("強い", "弱い"),
        ("一貫している", "整合性が低い"),
        ("目立つ", "目立たない"),
        ("分かりやすい", "分かりにくい")
    ]
    
    def validate_improvement_comments(
        self, 
        data: Dict[str, Any]
    ) -> Union[ImprovementCommentsSchema, LLMImprovementValidationError]:
        """
        改善コメントをバリデーション
        
        Args:
            data: LLM から返されたデータ（JSON）
        
        Returns:
            ImprovementCommentsSchema（成功）または LLMImprovementValidationError（失敗）
        """
        
        # 基本構造チェック
        if not isinstance(data, dict):
            return LLMImprovementValidationError(
                success=False,
                error_code="INVALID_STRUCTURE",
                reason="Response is not a dictionary"
            )
        
        if "comments" not in data:
            return LLMImprovementValidationError(
                success=False,
                error_code="MISSING_COMMENTS",
                reason="'comments' field is required"
            )
        
        comments = data.get("comments", [])
        if not isinstance(comments, list):
            return LLMImprovementValidationError(
                success=False,
                error_code="INVALID_COMMENTS_TYPE",
                reason="'comments' must be a list"
            )
        
        # 各コメントをバリデーション
        validated_comments = []
        errors = []
        
        for idx, comment_data in enumerate(comments):
            error = self._validate_single_comment(comment_data, idx)
            if error:
                errors.append(error)
            else:
                try:
                    comment = ImprovementComment(**comment_data)
                    validated_comments.append(comment)
                except Exception as e:
                    errors.append(f"Comment {idx}: {str(e)}")
        
        # エラーがあれば失敗
        if errors:
            return LLMImprovementValidationError(
                success=False,
                error_code="COMMENT_VALIDATION_FAILED",
                reason="; ".join(errors[:3])  # 最初の 3 個エラーのみ報告
            )
        
        # 成功
        return ImprovementCommentsSchema(
            comments=validated_comments,
            total_count=len(validated_comments),
            summary=data.get("summary", "")
        )
    
    def _validate_single_comment(self, comment_data: Dict[str, Any], index: int) -> str:
        """単一コメントの詳細チェック"""
        
        if not isinstance(comment_data, dict):
            return f"Comment {index}: not a dictionary"
        
        # 必須フィールド確認
        required = [
            "issue_summary", "target_scope", "evidence", 
            "recommended_action", "expected_impact"
        ]
        for field in required:
            if field not in comment_data or not comment_data[field]:
                return f"Comment {index}: missing or empty field '{field}'"
        
        issue_summary = str(comment_data.get("issue_summary", ""))
        target_scope = str(comment_data.get("target_scope", ""))
        evidence = str(comment_data.get("evidence", ""))
        recommended_action = str(comment_data.get("recommended_action", ""))
        
        # ===== 検査 1: 抽象語過多 =====
        abstract_found = []
        for word in self.ABSTRACT_WORDS:
            if word in issue_summary or word in recommended_action:
                abstract_found.append(word)
        
        if abstract_found:
            return f"Comment {index}: contains abstract words {abstract_found} without concrete details"
        
        # ===== 検査 2: 対象箇所の明確性 =====
        if len(target_scope) < 3:
            return f"Comment {index}: 'target_scope' too vague (must be specific)"
        
        # ===== 検査 3: 根拠の有無 =====
        if len(evidence) < 10:
            return f"Comment {index}: 'evidence' too short (must provide concrete reason)"
        
        # ===== 検査 4: 行動可能性 =====
        if "する" not in recommended_action and "を" not in recommended_action and "変更" not in recommended_action:
            # Note: "変更" is frequently used in actions.
            return f"Comment {index}: 'recommended_action' not concrete enough"
        
        # ===== 検査 5: 矛盾検知 =====
        contradiction = self._detect_contradiction(issue_summary, recommended_action)
        if contradiction:
            return f"Comment {index}: contradictory statements detected: {contradiction}"
        
        return ""  # エラーなし
    
    def _detect_contradiction(self, issue: str, action: str) -> str:
        """相反表現の検知"""
        
        for positive, negative in self.CONTRADICTORY_PAIRS:
            has_positive = positive in issue
            has_negative = negative in issue
            
            if has_positive and has_negative:
                return f"contains both '{positive}' and '{negative}'"
        
        return ""
