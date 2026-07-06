from pydantic.v1 import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from enum import Enum

# ===== 改善コメント用の新スキーマ =====

class PriorityLevel(str, Enum):
    """改善優先度"""
    P0 = "P0"  # 必須
    P1 = "P1"  # 強く推奨
    P2 = "P2"  # 推奨
    P3 = "P3"  # 参考

class ImprovementComment(BaseModel):
    """構造化改善コメント"""
    
    issue_summary: str = Field(..., description="問題の簡潔な要約", min_length=5, max_length=100)
    target_scope: str = Field(..., description="対象箇所（具体的な部位を明記）", min_length=3, max_length=50)
    evidence: str = Field(..., description="改善根拠（なぜそう判断したか）", min_length=10, max_length=200)
    recommended_action: str = Field(..., description="具体的な改善アクション", min_length=10, max_length=150)
    priority: PriorityLevel = Field(default=PriorityLevel.P2, description="優先度")
    expected_impact: str = Field(..., description="改善による期待効果", min_length=5, max_length=100)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="推奨の信頼度（0.0～1.0）")

class ImprovementCommentsSchema(BaseModel):
    """改善コメント集合（複数の観点）"""
    
    comments: List[ImprovementComment] = Field(default=[], description="改善コメントリスト")
    total_count: int = Field(default=0, description="改善コメント総数")
    summary: Optional[str] = Field(default=None, description="全体的な改善方針サマリー")

class LLMImprovementValidationError(BaseModel):
    """改善コメント生成時のバリデーションエラー（fail-soft）"""

    success: bool = False
    error_code: str = Field(..., description="エラーコード")
    reason: str = Field(..., description="エラー理由")
    fallback_content: Optional[Dict[str, Any]] = Field(default=None, description="代替内容（部分的に有効な結果）")


# ===== 意思決定支援（decision_support）用スキーマ =====
# 「強み・弱み・改善提案」を意思決定用に構造化するブロック。
# 既存の ImprovementCommentsSchema（diagnostics.improvements）とは独立した並存フィールドで、
# 後方互換のため diagnostics.decision_support は Optional として扱う（未生成・旧データでも欠落を許容）。

class DecisionSupportSummary(BaseModel):
    """結論サマリー（画面最上部のカードに使う）"""

    headline: str = Field(..., description="一言結論", min_length=5, max_length=80)
    decision: str = Field(..., description="継続 / 改修推奨 / 停止検討 等の短い判断ラベル", min_length=2, max_length=20)
    rationale: str = Field(..., description="判断理由（強み・弱みの要約）", min_length=10, max_length=200)


class StrengthItem(BaseModel):
    """強み: 今後も維持・再利用すべき勝ち要素（「よかった点」ではない）"""

    id: str = Field(..., description="weakness/recommendation から参照するための識別子")
    category: str = Field(..., description="visual/message/cta/target/lp/brand 等の短いラベル", min_length=2, max_length=20)
    title: str = Field(..., description="要素名", min_length=3, max_length=60)
    description: str = Field(..., description="何が良いかの具体説明", min_length=10, max_length=200)
    keep_reason: str = Field(..., description="今後も維持・再利用すべき理由", min_length=10, max_length=200)
    # Optional: 旧データや、LLMが省略した場合でもバリデーション失敗にしないため required にしない。
    evidence: Optional[str] = Field(
        default=None,
        description="分析データのどの部分からこの判断に至ったか（視線誘導/CTA/可読性/差別化/信頼性等の観点を含む短い根拠）",
        max_length=200,
    )


class WeaknessItem(BaseModel):
    """弱み: 成果の足を引っ張っているボトルネック"""

    id: str = Field(..., description="recommendation.target_weakness_ids から参照される識別子")
    priority: PriorityLevel = Field(..., description="P0（致命的）/ P1（改善推奨）/ P2（伸び代）")
    category: str = Field(..., description="visual/message/cta/target/lp/brand 等の短いラベル", min_length=2, max_length=20)
    title: str = Field(..., description="問題名", min_length=3, max_length=60)
    description: str = Field(..., description="何が問題かの具体説明", min_length=10, max_length=200)
    impact: str = Field(..., description="放置した場合の成果への影響", min_length=10, max_length=200)
    # Optional: 旧データや、LLMが省略した場合でもバリデーション失敗にしないため required にしない。
    evidence: Optional[str] = Field(
        default=None,
        description="分析データのどの部分からこの判断に至ったか（視線誘導/CTA/可読性/差別化/信頼性等の観点を含む短い根拠）",
        max_length=200,
    )


class RecommendationItem(BaseModel):
    """改善提案: What / Why / How の3点セットを必須とする"""

    id: str = Field(..., description="識別子")
    priority: PriorityLevel = Field(..., description="P0（致命的）/ P1（改善推奨）/ P2（伸び代）")
    target_weakness_ids: List[str] = Field(..., description="対応する weakness の id（最低1件）", min_length=1)
    title: str = Field(..., description="提案名", min_length=3, max_length=60)
    what: str = Field(..., description="何を変えるか（対象と変更内容）", min_length=10, max_length=200)
    why: str = Field(..., description="なぜ変えるか（対応する弱みへの言及を含む）", min_length=10, max_length=200)
    how: str = Field(..., description="どう検証するか（簡易な検証方法）", min_length=10, max_length=200)
    expected_effect: Optional[str] = Field(default=None, description="期待される効果", max_length=150)


class DecisionSupport(BaseModel):
    """意思決定支援ブロック（強み・弱み・改善提案）"""

    summary: DecisionSupportSummary = Field(..., description="結論サマリー")
    strengths: List[StrengthItem] = Field(default=[], description="強み（維持・再利用すべき勝ち要素）")
    weaknesses: List[WeaknessItem] = Field(default=[], description="弱み（ボトルネック）")
    recommendations: List[RecommendationItem] = Field(default=[], description="改善提案（What/Why/How必須）")


class LLMDecisionSupportValidationError(BaseModel):
    """decision_support 生成時のバリデーションエラー（fail-soft）"""

    success: bool = False
    error_code: str = Field(..., description="エラーコード")
    reason: str = Field(..., description="エラー理由")


class VisualsSchema(BaseModel):
    """画像・映像の視覚的特性"""
    dominant_colors: List[str] = Field(..., description="主要色リスト", min_length=1)
    composition: str = Field(..., description="構図の説明", min_length=5)
    style: str = Field(..., description="デザインスタイル", min_length=3)
    clarity: str = Field(..., description="視認性（高/中/低）", regex="^(高|中|低)$")
    
    class Config:
        strict = True

class ToneSchema(BaseModel):
    """トーン・メッセージング"""
    primary_tone: List[str] = Field(..., description="主要なトーン", min_length=1)
    emotional_appeal: str = Field(..., description="感情的訴求", regex="^(論理的|感情的|混合)$")
    call_to_action: str = Field(..., description="CTA の強度", regex="^(強|中|弱)$")
    
    class Config:
        strict = True

class CreativeCoreSchema(BaseModel):
    """CreativeCore の完全 Schema"""
    visuals: VisualsSchema = Field(..., description="ビジュアル分析")
    tone: ToneSchema = Field(..., description="トーン分析")
    ai_labels: List[str] = Field(..., description="AI ラベル", min_length=1, max_length=15)
    
    class Config:
        strict = True

class LLMResponseSchema(BaseModel):
    """LLM 分析結果の完全 Schema"""
    success: bool = Field(default=True)
    model: str = Field(..., description="使用モデル名")
    creative_core: Optional[CreativeCoreSchema] = Field(default=None, description="CreativeCore 分析結果")
    retry_count: int = Field(default=0, ge=0, le=3)
    error_details: Optional[str] = Field(default=None, description="エラー時の詳細")
    
    class Config:
        strict = True
