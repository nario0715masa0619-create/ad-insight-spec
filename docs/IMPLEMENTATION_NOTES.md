# 実装メモ - Ad-Insight-Spec Phase 1 Data Modeling

**Date**: 2026-06-22  
**Phase**: 1 (Data Modeling & Validation)

---

## 実装概要

本フェーズでは、JSON スキーマ仕様書 v0.1 を Pydantic + SQLAlchemy で実装し、**正本データモデルの固定**を達成しました。

### 成果物一覧

| ファイル | 役割 | ステータス |
|---------|------|----------|
| \ackend/app/schemas/ad_insight.py\ | Pydantic モデル（入れ子構造） | ✅ 完成 |
| \ackend/app/models/ad_insight.py\ | SQLAlchemy ORM モデル | ✅ 完成 |
| \ackend/app/core/config.py\ | 環境変数管理 | ✅ 完成 |
| \ackend/app/db/base.py\ | DB Base クラス | ✅ 完成 |
| \ackend/app/db/session.py\ | DB セッション管理 | ✅ 完成 |
| \ackend/requirements.txt\ | 依存ライブラリ | ✅ 完成 |
| \docs/specs/ad_insight_json_schema_v0_1.md\ | v0.1 スキーマ仕様 | ✅ 完成 |
| \scripts/validate_sample_data.py\ | サンプルデータ検証 | ✅ 完成 |
| \docs/IMPLEMENTATION_NOTES.md\ | このドキュメント | ✅ 完成 |

---

## 実装詳細

### 1. Pydantic モデル設計

**目的**: JSON スキーマを入れ子構造で完全に表現

**特徴**:
- 7つのトップレベルセクション + 各種ネストモデル
- 各フィールドに詳細な description を付与（API ドキュメント自動生成対応）
- alias （特に \_metadata\ ）を使用して JSON キー互換性を確保
- Validation: \ge\, \le\ で数値範囲チェック

**クラス階層**:
\\\
AdInsightCreate
  ├─ AssetMeta
  │   └─ AnalysisPeriod
  ├─ CreativeCore
  │   ├─ AILabels (optional)
  │   └─ PlatformSpecific (extra="allow")
  ├─ LandingPage
  ├─ Performance
  ├─ Diagnostics
  ├─ Views
  │   └─ DashboardSummary
  └─ Metadata

AdInsight(AdInsightCreate)
  └─ + id, created_at, updated_at
\\\

### 2. SQLAlchemy モデル設計

**目的**: MVP レベルのシンプルな DB 設計（後の正規化に対応）

**特徴**:
- 単一テーブル \d_insights\ で全データを保持
- \sset_meta, creative_core\ 等は JSON カラムで保存（柔軟性確保）
- \d_id\ は UNIQUE INDEX（Pydantic の unique制約に対応）
- \platform\ INDEX で複数媒体対応を見据えた設計

**テーブル構造**:
\\\sql
ad_insights:
  - id (PK)
  - ad_id (UNIQUE, INDEX)
  - platform (INDEX)
  - campaign_name, adset_name, ad_name
  - analysis_period_start, analysis_period_end
  - asset_meta (JSON)
  - creative_core (JSON)
  - landing_page (JSON)
  - performance (JSON)
  - diagnostics (JSON)
  - views (JSON)
  - _metadata (JSON)
  - data_source, ai_model_version
  - created_at, updated_at (timestamps)
\\\

### 3. 環境変数管理

**ファイル**: \~/.ad-insight-spec/.env\

**環境変数一覧**:
\\\
DATABASE_URL=postgresql://user:password@localhost:5432/ad_insight_spec
GEMINI_API_KEY=xxx
OPENAI_API_KEY=xxx
META_GRAPH_API_KEY=xxx
DEBUG=false
\\\

**読み込み**:
- Pydantic Settings で自動読み込み
- デフォルト値を定義（開発環境向け）

---

## Strict フィールド vs Optional フィールド

### なぜ分けたのか？

**Strict（必須）フィールド**:
- これが欠けると、分析や診断の信頼性が低下
- マーケターへの提示価値が 0 になる可能性
- 例: CPA, CVR, 改善提案等

**Optional フィールド**:
- LLM 生成結果（AI Labels）
- 高度な分析用（ROAS, reach, frequency）
- ダッシュボード表示用計算値（ranking, trend）
- 媒体特有フィールド（future-proofing）

### 判定テーブル

| フィールド | Strict? | 理由 |
|-----------|--------|------|
| ad_id | ✅ | 一意識別が必須 |
| platform | ✅ | 媒体判定が必須 |
| impressions, clicks, ctr | ✅ | KPI 計算に必須 |
| cpa, cvr | ✅ | 診断ロジックに直結 |
| ai_labels | ❌ | LLM は optional（初期段階） |
| reach, frequency | ❌ | CPA あれば MVP 動作可 |
| platform_specific | ❌ | Meta特有情報（拡張用） |
| recommended_actions | ✅ | マーケターへの提示価値の中核 |

---

## サンプルデータ検証結果

### 実行コマンド

\\\ash
cd C:\\NewProjects\\ad-insight-spec
python scripts/validate_sample_data.py
\\\

### 期待される出力

\\\
🔍 Validating 3 sample files...

✅ meta_ad_sample_fatigue.json
   ✓ Valid AdInsight (ad_id: ad_556677889_fatigue)

✅ meta_ad_sample_good.json
   ✓ Valid AdInsight (ad_id: ad_987654321_good)

✅ meta_ad_sample_lp_mismatch.json
   ✓ Valid AdInsight (ad_id: ad_223344556_lp_issue)

------------------------------------------------------------
📊 Summary: 3/3 files valid
✅ All sample data is valid!
\\\

---

## 拡張ポイント・将来への対応

### 1. Google Ads 対応

**現在（Meta特化）**:
\\\python
platform_specific: {
    "placement": "ig_feed",
    "objective": "OUTCOME_SALES"
}
\\\

**将来（Google対応）**:
\\\python
platform_specific: {
    "placement": "google_search",
    "ad_type": "text_ads"
}
\\\

**対応**: \xtra = "allow"\ で自動対応

### 2. テーブル分割（正規化）

**現在（MVP）**: 単一テーブル + JSON カラム

**将来（分析効率化時）**:
\\\sql
-- performance を専用テーブルに
CREATE TABLE performance_metrics (
    id PK,
    ad_insight_id FK,
    impressions, clicks, ctr, spend, conversions, cpa, cvr
);

-- creative 要素を専用テーブルに
CREATE TABLE creative_elements (
    id PK,
    ad_insight_id FK,
    hook_type, appeal_axis, emotion, tone
);
\\\

**対応**: SQLAlchemy リレーション追加で対応可能

### 3. AI Labels の LLM 自動生成

**現在**: optional（LLM 生成待ち）

**将来（Phase 2）**:
- Converter Service で自動抽出
- Gemini/OpenAI API 呼び出し
- キャッシング機構で API コスト削減

---

## Open Questions & Decisions Pending

### Q1. CTR は「実績値」か「計算値」か？

**現在の判断**: 実績値として strict にしている

**理由**: Meta API から直接取得可能（計算の必要がない）

**将来の検討**: CSV インポート時に \clicks / impressions\ で補完する logic

### Q2. Form Difficulty はどのように検出するか？

**現在**: Optional（手動入力またはスクレイピング推定）

**将来**: LP スクレイピング時に Selenium で DOM 解析、form field 数から推定

### Q3. Message Match Score の算出アルゴリズム

**現在**: 手動入力またはLLM 評価（値は 0.0～1.0）

**将来の検討**:
- キーワード抽出（広告・LP 両方）
- 一致度スコア = 共通キーワード数 / 合計キーワード数
- LLM による意味的マッチング

### Q4. データベース永続化のタイミング

**現在の方針**: 
- Converter で JSON 生成 → Pydantic 検証 → SQLAlchemy 保存

**検討中**: 
- キャッシング層？（同一広告の二重処理防止）
- Update Logic？（同一 ad_id で新しい analysis_period が来た場合）

---

## チェックリスト - Phase 1 Data Modeling

- ✅ Pydantic モデル実装完成
- ✅ SQLAlchemy モデル実装完成
- ✅ 環境変数管理完成
- ✅ サンプルデータ 3件が全て validate 可能
- ✅ JSON スキーマ v0.1 確定
- ✅ Strict/Optional フィールド判定完了
- ⏳ Alembic マイグレーション（Phase 2 で実装）
- ⏳ FastAPI エンドポイント（Phase 2 で実装）
- ⏳ Meta API クライアント（Phase 2 で実装）

---

## 次のステップ（Phase 2 準備）

### 実装順序

1. **Alembic 初期化** - \lembic init\ + migration file 作成
2. **Repository Pattern** - CRUD 実装 (\ackend/app/repositories/ad_repository.py\)
3. **FastAPI Endpoints** - 
   - \POST /api/v1/ad-insights\ - 作成
   - \GET /api/v1/ad-insights/{ad_id}\ - 取得
   - \GET /api/v1/ad-insights\ - リスト（フィルタ対応）
4. **Meta Ads API Client** - データ取込み
5. **Converter Service** - JSON 生成ロジック

---

## 参考資料

- JSON Schema v0.1: \docs/specs/ad_insight_json_schema_v0_1.md\
- Pydantic Docs: https://docs.pydantic.dev/
- SQLAlchemy Docs: https://docs.sqlalchemy.org/
- FastAPI Docs: https://fastapi.tiangolo.com/
