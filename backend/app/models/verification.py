from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
from app.db.base import Base


class VerificationCase(Base):
    """
    検証案件。

    CampaignPilotの提案がMeta Ads Managerだけでは出にくい新規の原因特定・改善案を
    生んでいるかを記録するための最上位単位。1案件 = 1クライアント/1ヒアリングセッション。
    既存の ad_insights テーブルとは asset_id で緩く紐づくのみで、外部キー制約は張らない
    （ad_insights はバージョニングされたテーブルのため、結合の複雑化を避ける）。

    asset_id を指定する場合、asset_version（提示した時点の分析結果のバージョン）も
    必須とする。ヒアリング〜評価の間に同じ asset_id で再分析が走っても、提示した
    版がずれて参照されないようにするため（CHECK制約でDB側でも強制する）。
    """

    __tablename__ = "verification_cases"

    id: int = Column(Integer, primary_key=True, index=True)

    case_name: str = Column(String(200), nullable=False)

    # ad_insights.asset_id への緩い紐付け（任意、FK制約なし）
    asset_id: Optional[str] = Column(String(100), nullable=True, index=True)

    # asset_id が指定されている場合、提示した時点のバージョンを固定するため必須
    asset_version: Optional[int] = Column(Integer, nullable=True)

    # 事前ヒアリング内容（構造は決め打ちしない自由記述中心のJSON）
    pre_hearing_notes: Optional[dict] = Column(JSON, nullable=True)

    # CampaignPilot提示後の総合評価
    presentation_evaluation: Optional[dict] = Column(JSON, nullable=True)

    created_at: datetime = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "asset_id IS NULL OR asset_version IS NOT NULL",
            name="ck_verification_cases_asset_version_required_with_asset_id",
        ),
    )

    def __repr__(self):
        return f"<VerificationCase(id={self.id}, case_name='{self.case_name}')>"


class VerificationSuggestionEvaluation(Base):
    """
    案件内の個別提案に対する評価。

    提案の内容自体は分析結果スキーマ(decision_support/axes等)から自動抽出せず、
    評価者が都度手入力する（分析スキーマの変更に影響されないようにするため）。
    """

    __tablename__ = "verification_suggestion_evaluations"

    id: int = Column(Integer, primary_key=True, index=True)

    case_id: int = Column(Integer, ForeignKey("verification_cases.id"), nullable=False, index=True)

    # 提案タイトル/短い識別ラベル
    suggestion_key: str = Column(String(300), nullable=False)

    # 提案内容のコピー（任意）
    suggestion_text: Optional[str] = Column(Text, nullable=True)

    # 「既に気づいていた / 言われて初めて気づいた / 妥当性に疑問 / 判断不能」
    awareness_rating: str = Column(String(50), nullable=False)

    # 「自分でも出していた / 自分では先に出せなかった / 一般論 / 実行しにくい / 不要」
    originality_rating: str = Column(String(50), nullable=False)

    created_at: datetime = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_verification_suggestion_case", "case_id", "created_at"),
    )

    def __repr__(self):
        return f"<VerificationSuggestionEvaluation(id={self.id}, case_id={self.case_id}, suggestion_key='{self.suggestion_key}')>"


class VerificationFollowup(Base):
    """
    提案ごとの2週間後・4週間後の実行有無と成果変化の記録。

    1提案 x 1チェックポイント(week_2/week_4)につき1レコード。
    同じチェックポイントへの再送信は upsert として扱う。
    """

    __tablename__ = "verification_followups"

    id: int = Column(Integer, primary_key=True, index=True)

    suggestion_evaluation_id: int = Column(
        Integer, ForeignKey("verification_suggestion_evaluations.id"), nullable=False, index=True
    )

    # "week_2" または "week_4"
    checkpoint: str = Column(String(20), nullable=False)

    executed: Optional[bool] = Column(Boolean, nullable=True)
    result_change: Optional[str] = Column(Text, nullable=True)

    recorded_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("suggestion_evaluation_id", "checkpoint", name="uq_followup_suggestion_checkpoint"),
    )

    def __repr__(self):
        return f"<VerificationFollowup(id={self.id}, suggestion_evaluation_id={self.suggestion_evaluation_id}, checkpoint='{self.checkpoint}')>"
