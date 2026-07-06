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


# ===== 5軸構造化（appeal/creative/cta/trust/target） =====
# 「抽象的で現場の業務に使えない」という課題への対応として、strengths/weaknesses/recommendations の
# フラットリストを廃し、固定5軸 × 強み/弱み/改善提案の3点セット必須構造に作り替える。
# 旧形式（axes なし）で既に保存されているデータは、このモデルへ再構築せず
# フロントエンドが raw dict のまま従来通り読む（後方互換・データ移行不要）。

EVALUATION_AXES = [
    ("appeal", "訴求軸"),
    ("creative", "クリエイティブ"),
    ("cta", "CTA"),
    ("trust", "信頼"),
    ("target", "ターゲット"),
]
AXIS_IDS = [axis_id for axis_id, _ in EVALUATION_AXES]
AXIS_LABELS = dict(EVALUATION_AXES)


class Evidence(BaseModel):
    """判断根拠の4点セット（対象箇所・観点・評価・根拠）を必須とする"""

    location: str = Field(
        ...,
        description="対象箇所（テキスト抜粋・動画タイムスタンプ等、後から見返しても位置が分かる形式）",
        min_length=2,
        max_length=100,
    )
    viewpoint: str = Field(..., description="評価観点（訴求軸/視線誘導/CTA/可読性/差別化/信頼性等）", min_length=2, max_length=40)
    evaluation: str = Field(..., description="その観点から見た評価", min_length=2, max_length=100)
    rationale: str = Field(..., description="なぜそう評価するかの根拠", min_length=5, max_length=200)


class AxisStrength(BaseModel):
    """軸ごとの強み: 今後も維持・再利用すべき勝ち要素"""

    target_element: str = Field(
        ...,
        description="対象要素の特定（例: ファーストビューのテキスト、動画5〜8秒目、CTAボタン文言等）",
        min_length=2,
        max_length=80,
    )
    description: str = Field(..., description="何が良いかの具体説明", min_length=10, max_length=200)
    reason: str = Field(..., description="強みと判断した理由（ユーザー心理・ベストプラクティスの観点）", min_length=10, max_length=200)
    keep_reason: str = Field(..., description="今後も維持・再利用すべき理由", min_length=10, max_length=200)
    evidence: Evidence = Field(..., description="判断根拠（対象箇所・観点・評価・根拠の4点セット）")


class AxisWeakness(BaseModel):
    """軸ごとの弱み: 成果の足を引っ張っているボトルネック"""

    target_element: str = Field(..., description="対象要素の特定", min_length=2, max_length=80)
    description: str = Field(..., description="何が問題かの具体説明", min_length=10, max_length=200)
    reason: str = Field(..., description="弱みと判断した理由（ユーザー心理・ベストプラクティスの観点）", min_length=10, max_length=200)
    impact: str = Field(..., description="放置した場合の成果への影響", min_length=10, max_length=200)
    evidence: Evidence = Field(..., description="判断根拠（対象箇所・観点・評価・根拠の4点セット）")


class AxisRecommendation(BaseModel):
    """軸ごとの改善提案: What / Why / How + 期待効果を必須とする"""

    what: str = Field(..., description="何を変えるか（対象と変更内容を具体的に）", min_length=10, max_length=200)
    why: str = Field(..., description="なぜ変えるか（対応する弱みへの言及を含む）", min_length=10, max_length=200)
    how: str = Field(..., description="どう検証するか（簡易な検証方法）", min_length=10, max_length=200)
    expected_effect: str = Field(
        ...,
        description="期待される効果（理解速度向上・CVR改善・CTR向上等、具体的な指標で）",
        min_length=5,
        max_length=150,
    )


class AxisBlock(BaseModel):
    """評価軸1件分（強み・弱み・改善提案の3点セットを必須とする）"""

    axis: str = Field(..., description=f"固定5軸のいずれか: {AXIS_IDS}")
    axis_label: str = Field(..., description="軸の日本語ラベル")
    score: int = Field(..., ge=1, le=5, description="この軸の評価スコア（1〜5）")
    strength: AxisStrength = Field(..., description="この軸の強み")
    weakness: AxisWeakness = Field(..., description="この軸の弱み")
    recommendation: AxisRecommendation = Field(..., description="この軸の改善提案")

    @validator("axis")
    def axis_must_be_known(cls, v):
        if v not in AXIS_IDS:
            raise ValueError(f"axis must be one of {AXIS_IDS}, got '{v}'")
        return v


class DecisionSupport(BaseModel):
    """意思決定支援ブロック（5軸 × 強み・弱み・改善提案）"""

    summary: DecisionSupportSummary = Field(..., description="結論サマリー")
    axes: List[AxisBlock] = Field(..., description="5軸の評価（appeal/creative/cta/trust/target）", min_items=5, max_items=5)
    # overall_score/overall_rank は LLM 出力を信頼せず、validator 通過後に llm_service 側で
    # axes のスコア平均から算出してセットする（生成時点では未設定 = None）。
    overall_score: Optional[float] = Field(default=None, description="総合スコア（軸スコア平均、Python側で算出）")
    overall_rank: Optional[str] = Field(default=None, description="総合ランク A/B/C/D（Python側で算出）")

    # [非推奨・後方互換用] axes 導入前の旧形式データ用フィールド。新規生成では使用しない。
    strengths: List[StrengthItem] = Field(default=[], description="[非推奨] 旧形式の強みリスト")
    weaknesses: List[WeaknessItem] = Field(default=[], description="[非推奨] 旧形式の弱みリスト")
    recommendations: List[RecommendationItem] = Field(default=[], description="[非推奨] 旧形式の改善提案リスト")


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
