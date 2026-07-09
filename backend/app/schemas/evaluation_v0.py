"""
evaluation_data (v0) スキーマ — Phase 1（DBカラム追加 + v0スキーマ導入）。

`AdInsight.evaluation_data`（nullable JSON、backend/app/models/ad_insight.py）に
将来格納される「評価・解釈」ブロックの形状を定義する。現時点ではこのスキーマを
使って実際にデータを生成・保存するコードは無い（dual-writeはPhase 3）。

`diagnostics`/`performance`/`landing_page_analysis` は既存の
`app.schemas.ad_insight` の型をそのまま再利用する（評価結果の中身自体は
asset/evaluation分割によって変わらないため、新しい型を作らない）。

オープン課題3（`_metadata`再構成方針）の解決:
legacy `Metadata`（spec_data._metadata、`app.schemas.ad_insight.Metadata`）の
9フィールドは「取り込み時に確定する情報」と「評価実行時に確定する情報」が
混在していた。前者は `asset_v0.AssetMetaV0`（created_at/analysis_version等）に、
後者は本ファイルの `EvaluationMetaV0` に分割する:

| legacy Metadata フィールド | 移動先 |
|---|---|
| generated_at, data_source, input_mode | asset_v0.AssetMetaV0（取り込み時点の情報） |
| ai_model_version | EvaluationMetaV0.evaluator_model |
| processing_time_ms, validation_status, validation_notes, analysis_tools_used | EvaluationMetaV0（評価実行時の情報） |
| json_schema_version | 将来の downcast 実装時に固定値 "v0.2" を補うか、
  AssetJsonV0/EvaluationJsonV0双方に持たせるスキーマバージョンから導出するかは
  Phase 2のdowncast実装時に決定する（本Phaseのスコープ外） |

既知の落とし穴: `EvaluationMetaV0.evaluated_at` は `datetime` 型のため、
保存時は `.dict()` ではなく `json.loads(model.json())` を経由すること
（asset_v0.py と同じ理由。実際に保存するコードはPhase 3で書かれる）。
"""
from typing import Optional, List
from datetime import datetime

from pydantic.v1 import BaseModel, Field

from app.schemas.ad_insight import Diagnostics, Performance, LandingPage, AnalysisToolsUsed


class EvaluationMetaV0(BaseModel):
    """evaluation_data.evaluation_meta"""
    evaluated_at: datetime = Field(..., description="評価実行時刻（ISO 8601）")
    evaluator_model: str = Field(..., description="gemini-2.0-flash / gpt-4o / claude-opus 等")
    processing_time_ms: Optional[int] = Field(None, description="処理時間（ミリ秒）")
    validation_status: Optional[str] = Field(None, description="passed / warnings / failed")
    validation_notes: Optional[List[str]] = Field(None, description="バリデーション時のメモ")
    analysis_tools_used: Optional[AnalysisToolsUsed] = Field(None)


class EvaluationJsonV0(BaseModel):
    """AdInsight.evaluation_data に格納される全体構造"""
    evaluation_meta: EvaluationMetaV0
    diagnostics: Diagnostics
    performance: Optional[Performance] = Field(None)
    landing_page_analysis: Optional[LandingPage] = Field(None)
