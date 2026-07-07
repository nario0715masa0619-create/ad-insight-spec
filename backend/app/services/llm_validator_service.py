import re
from typing import Union, List, Dict, Any
from app.schemas.llm_response import (
    ImprovementCommentsSchema,
    ImprovementComment,
    LLMImprovementValidationError,
    DecisionSupport,
    DecisionSupportSummary,
    AxisBlock,
    AXIS_IDS,
    LLMDecisionSupportValidationError,
    VideoCutContent,
    VideoCutAnalysis,
    LLMVideoCutAnalysisValidationError,
)
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

    # ===== expected_effect が具体的な指標に言及しているかの軽量チェック用キーワード =====
    EXPECTED_EFFECT_METRIC_KEYWORDS = [
        "CVR", "CTR", "CPA", "CPC", "率", "速度", "時間", "%", "％",
        "視聴", "離脱", "完了率", "改善", "向上", "増加", "減少",
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

    # ===== 意思決定支援（decision_support）バリデーション =====

    def validate_decision_support(
        self,
        data: Dict[str, Any]
    ) -> Union[DecisionSupport, LLMDecisionSupportValidationError]:
        """
        decision_support（5軸 × 強み・弱み・改善提案）をバリデーション

        - summary / axes の必須構造を確認
        - axes が固定5軸（AXIS_IDS）を過不足・重複なくちょうど1件ずつカバーしているか確認
        - 各軸を Pydantic モデル（AxisBlock）で検証
        - strength/weakness の本文に抽象語が含まれないか検査
        - recommendation.expected_effect が具体的な指標語を含むか検査
        """
        if not isinstance(data, dict):
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="INVALID_STRUCTURE",
                reason="Response is not a dictionary"
            )

        for required_field in ("summary", "axes"):
            if required_field not in data:
                return LLMDecisionSupportValidationError(
                    success=False,
                    error_code="MISSING_FIELD",
                    reason=f"'{required_field}' field is required"
                )

        summary_data = data.get("summary")
        if not isinstance(summary_data, dict):
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="INVALID_SUMMARY",
                reason="'summary' must be an object"
            )
        try:
            summary = DecisionSupportSummary(**summary_data)
        except Exception as e:
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="SUMMARY_VALIDATION_FAILED",
                reason=str(e)
            )

        axes_data = data.get("axes", [])
        if not isinstance(axes_data, list):
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="INVALID_LIST_TYPE",
                reason="'axes' must be a list"
            )

        # ===== 軸の過不足・重複チェック（AxisBlock 個別のバリデーションより先に行う） =====
        axis_ids_seen = [item.get("axis") for item in axes_data if isinstance(item, dict)]
        missing_axes = [a for a in AXIS_IDS if a not in axis_ids_seen]
        unknown_axes = [a for a in axis_ids_seen if a not in AXIS_IDS]
        duplicate_axes = [a for a in AXIS_IDS if axis_ids_seen.count(a) > 1]
        if missing_axes or unknown_axes or duplicate_axes:
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="AXIS_COVERAGE_INVALID",
                reason=(
                    f"axes must cover exactly {AXIS_IDS} once each; "
                    f"missing={missing_axes}, unknown={unknown_axes}, duplicate={duplicate_axes}"
                )
            )

        errors: List[str] = []
        axes: List[AxisBlock] = []
        for idx, item in enumerate(axes_data):
            axis_id = item.get("axis") if isinstance(item, dict) else None
            try:
                axis_block = AxisBlock(**item)
            except Exception as e:
                errors.append(f"axis {axis_id or idx}: {str(e)}")
                continue

            strength = axis_block.strength
            weakness = axis_block.weakness
            recommendation = axis_block.recommendation

            abstract_found = [
                w for w in self.ABSTRACT_WORDS
                if w in strength.description or w in strength.reason
                or w in weakness.description or w in weakness.reason or w in weakness.impact
            ]
            if abstract_found:
                errors.append(f"axis {axis_block.axis}: contains abstract words {abstract_found}")
                continue

            has_metric_keyword = any(
                kw in recommendation.expected_effect for kw in self.EXPECTED_EFFECT_METRIC_KEYWORDS
            )
            if not has_metric_keyword:
                errors.append(
                    f"axis {axis_block.axis}: 'expected_effect' does not mention a concrete/measurable outcome"
                )
                continue

            axes.append(axis_block)

        if errors:
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="ITEM_VALIDATION_FAILED",
                reason="; ".join(errors[:3])
            )

        # AXIS_IDS の順に並べ替え、フロント側での表示順を安定させる
        axes_by_id = {axis.axis: axis for axis in axes}
        ordered_axes = [axes_by_id[axis_id] for axis_id in AXIS_IDS]

        return DecisionSupport(
            summary=summary,
            axes=ordered_axes,
        )

    # ===== カット別分析（video_cuts）バリデーション =====

    def validate_video_cuts(
        self,
        data: Dict[str, Any],
        known_cut_ids: List[str],
    ) -> Union[VideoCutAnalysis, LLMVideoCutAnalysisValidationError]:
        """
        video_cuts（カット別分析）をバリデーション

        - "cuts" の必須構造を確認
        - known_cut_ids（バックエンド側で確定済みのカットID）を過不足・重複
          なくカバーしているか確認（validate_decision_support の軸カバレッジ
          チェックと同じロジック）
        - 各カットを Pydantic モデル（VideoCutContent）で検証
        - summary/strength_or_issue/improvement_suggestion に抽象語が
          含まれないか検査
        """
        if not isinstance(data, dict):
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="INVALID_STRUCTURE",
                reason="Response is not a dictionary"
            )

        if "cuts" not in data:
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="MISSING_FIELD",
                reason="'cuts' field is required"
            )

        cuts_data = data.get("cuts", [])
        if not isinstance(cuts_data, list):
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="INVALID_LIST_TYPE",
                reason="'cuts' must be a list"
            )

        cut_ids_seen = [item.get("cut_id") for item in cuts_data if isinstance(item, dict)]
        missing_cuts = [c for c in known_cut_ids if c not in cut_ids_seen]
        unknown_cuts = [c for c in cut_ids_seen if c not in known_cut_ids]
        duplicate_cuts = [c for c in known_cut_ids if cut_ids_seen.count(c) > 1]
        if missing_cuts or unknown_cuts or duplicate_cuts:
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="CUT_COVERAGE_INVALID",
                reason=(
                    f"cuts must cover exactly {known_cut_ids} once each; "
                    f"missing={missing_cuts}, unknown={unknown_cuts}, duplicate={duplicate_cuts}"
                )
            )

        errors: List[str] = []
        cuts: List[VideoCutContent] = []
        for idx, item in enumerate(cuts_data):
            cut_id = item.get("cut_id") if isinstance(item, dict) else None
            try:
                cut = VideoCutContent(**item)
            except Exception as e:
                errors.append(f"cut {cut_id or idx}: {str(e)}")
                continue

            abstract_found = [
                w for w in self.ABSTRACT_WORDS
                if w in cut.summary or w in cut.strength_or_issue or w in cut.improvement_suggestion
            ]
            if abstract_found:
                errors.append(f"cut {cut.cut_id}: contains abstract words {abstract_found}")
                continue

            cuts.append(cut)

        if errors:
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="ITEM_VALIDATION_FAILED",
                reason="; ".join(errors[:3])
            )

        # known_cut_ids の順に並べ替え、フロント側での表示順を安定させる
        cuts_by_id = {c.cut_id: c for c in cuts}
        ordered_cuts = [cuts_by_id[cid] for cid in known_cut_ids]

        return VideoCutAnalysis(cuts=ordered_cuts)
