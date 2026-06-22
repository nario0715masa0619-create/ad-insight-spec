# JSON スキーマ仕様書 - Ad-Insight-Spec v0.1

**Version**: 0.1  
**Date**: 2026-06-22  
**Status**: APPROVED (Phase 1 実装用)

## 概要

本ドキュメントは、\d_insight_json_schema_draft.md\ をベースに、**Phase 1 実装用に確定した v0.1 仕様書**です。

Pydantic スキーマおよび SQLAlchemy モデルの実装依拠文書として機能します。

---

## トップレベル構造

\\\json
{
  "asset_meta": { ... },
  "creative_core": { ... },
  "landing_page": { ... },
  "performance": { ... },
  "diagnostics": { ... },
  "views": { ... },
  "_metadata": { ... }
}
\\\

---

## フィールド定義 - Strict vs Optional

### 1. asset_meta

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| ad_id | string | ✅ **strict** | 一意ID、255文字以下 |
| platform | string | ✅ **strict** | meta, google, tiktok等 |
| campaign_name | string | ✅ **strict** | 255文字以下 |
| adset_name | string | ✅ **strict** | 255文字以下 |
| ad_name | string | ✅ **strict** | 255文字以下 |
| analysis_period.start | string | ✅ **strict** | ISO 8601 (YYYY-MM-DD) |
| analysis_period.end | string | ✅ **strict** | ISO 8601 (YYYY-MM-DD) |

### 2. creative_core

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| format | string | ✅ **strict** | static_image, video, carousel_image等 |
| primary_text | string | ✅ **strict** | 本文テキスト |
| headline | string | ✅ **strict** | 見出し |
| call_to_action | string | ✅ **strict** | CTA テキスト |
| ai_labels | object | ❌ optional | LLM 生成（Hook/Appeal/Audience/Emotion/Tone） |
| platform_specific | object | ❌ optional | Meta特有: placement, objective, budget等 |

### 3. landing_page

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| url | string | ✅ **strict** | URL 形式 |
| fv_copy | string | ✅ **strict** | ファーストビュー訴求文 |
| offer | string | ✅ **strict** | オファー内容 |
| form_difficulty | string | ❌ optional | low, medium, high |
| match_score_with_ad | float | ❌ optional | 0.0～1.0（メッセージマッチ） |

### 4. performance

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| impressions | integer | ✅ **strict** | ≥ 0 |
| clicks | integer | ✅ **strict** | ≥ 0 |
| ctr | float | ✅ **strict** | 0.0～1.0 |
| spend | float | ✅ **strict** | ≥ 0.0 |
| conversions | integer | ✅ **strict** | ≥ 0 |
| cpa | float | ✅ **strict** | ≥ 0.0 |
| cvr | float | ✅ **strict** | 0.0～1.0 |
| reach | integer | ❌ optional | ≥ 0 |
| frequency | float | ❌ optional | ≥ 0.0 |
| roas | float | ❌ optional | ≥ 0.0 |

### 5. diagnostics

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| creative_fatigue_risk | string | ✅ **strict** | low, medium, high |
| performance_status | string | ✅ **strict** | excellent, good, fair, poor |
| lp_message_match_risk | string | ❌ optional | low, medium, high |
| recommended_actions | array[string] | ✅ **strict** | 改善提案リスト（1件以上） |

### 6. views

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| dashboard_summary.status_label | string | ✅ **strict** | Excellent, Good, Fair, Poor |
| dashboard_summary.key_metric_highlight | string | ✅ **strict** | ハイライトテキスト |
| performance_ranking | string | ❌ optional | Top 10%, Bottom 30%等 |
| trend_indicator | string | ❌ optional | ↑ +15%, ↓ -58%等 |

### 7. _metadata

| フィールド | 型 | 必須 | Validation |
|-----------|-----|------|-----------|
| generated_at | string | ✅ **strict** | ISO 8601 (YYYY-MM-DDTHH:MM:SSZ) |
| data_source | string | ✅ **strict** | meta_graph_api, csv_import, manual_input等 |
| ai_model_version | string | ✅ **strict** | gemini-2.0, gpt-4o等 |
| version | string | ✅ **strict** | JSON スキーマバージョン（現在 1.0） |

---

## Strict vs Optional - 設計理由

### Strict フィールド（✅ 必須）

**理由**: これらが欠けると、分析・診断・レポートの信頼性が低下する。

- **asset_meta**: 「どの広告か」を一意に特定するため
- **creative_core**: メインメッセージの解析に必須
- **landing_page**: 広告・LPマッチスコア算出に必須
- **performance**: KPI計算に必須
- **diagnostics**: マーケター向けの結論提示に必須
- **_metadata**: トレーサビリティに必須

### Optional フィールド（❌ あると嬉しい、なくても OK）

**理由**: LLM生成や高度な分析の追加情報であり、MVP段階では不要。

- **ai_labels**: LLM が自動生成（初期段階ではスキップ可能）
- **platform_specific**: Meta特有情報（future-proofing用）
- **reach, frequency, roas**: 高度な分析用（CTR、CVR、CPA あれば最小限可）
- **performance_ranking, trend_indicator**: ダッシュボード表示用（計算で生成可能）

---

## SQLAlchemy テーブル設計（MVP）

### ad_insights テーブル

\\\sql
CREATE TABLE ad_insights (
    id INTEGER PRIMARY KEY,
    ad_id VARCHAR(255) UNIQUE NOT NULL,
    platform VARCHAR(50) NOT NULL,
    campaign_name VARCHAR(255) NOT NULL,
    adset_name VARCHAR(255) NOT NULL,
    ad_name VARCHAR(255) NOT NULL,
    analysis_period_start VARCHAR(10) NOT NULL,
    analysis_period_end VARCHAR(10) NOT NULL,
    
    -- JSON ペイロード（柔軟性保持）
    asset_meta JSON NOT NULL,
    creative_core JSON NOT NULL,
    landing_page JSON NOT NULL,
    performance JSON NOT NULL,
    diagnostics JSON NOT NULL,
    views JSON NOT NULL,
    _metadata JSON NOT NULL,
    
    -- メタデータ
    data_source VARCHAR(50),
    ai_model_version VARCHAR(50),
    created_at TIMESTAMP WITH TIMEZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()
);

CREATE INDEX idx_ad_insights_ad_id ON ad_insights(ad_id);
CREATE INDEX idx_ad_insights_platform ON ad_insights(platform);
\\\

### 設計方針

**なぜ JSON カラムか？**
1. MVP段階では、完全正規化は過剰
2. LLM出力 (ai_labels) や媒体特有フィールドの柔軟性を保つ
3. 将来、分析効率化に応じて個別テーブルに分割可能

---

## 実装対象（Phase 1）

### ✅ 実装済み

- \ackend/app/schemas/ad_insight.py\ - Pydantic モデル（全7層、入れ子構造完全）
- \ackend/app/models/ad_insight.py\ - SQLAlchemy モデル
- \ackend/app/core/config.py\ - 設定管理
- \ackend/app/db/base.py\ - DB Base
- \ackend/app/db/session.py\ - DB セッション
- \ackend/requirements.txt\ - 依存ライブラリ

### ⏳ Phase 1 で実装予定

- Meta Ads API クライアント (\ackend/app/services/meta_service.py\)
- Converter / 要素分解 (\ackend/app/services/converter_service.py\)
- LP スクレイピング (\ackend/app/services/lp_service.py\)
- Repository パターン (\ackend/app/repositories/ad_repository.py\)
- FastAPI エンドポイント (\ackend/app/api/ads.py\)

---

## 拡張ポイント（Cross-Platform Ready）

### 現在（Meta特化）

\\\python
platform_specific: {
    "placement": "ig_feed",
    "objective": "OUTCOME_SALES",
    "budget": 80000
}
\\\

### 将来（Google Ads対応）

\\\python
platform_specific: {
    "placement": "google_search",
    "ad_type": "text_ads",
    "conversion_value": 5000
}
\\\

**設計**: \platform_specific\ に \xtra = "allow"\ で対応
