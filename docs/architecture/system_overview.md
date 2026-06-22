# JSON スキーマ仕様書（ドラフト）- Ad-Insight-Spec

## 概要

Web広告とランディングページを分析するための構造化JSON形式。VIS の 3層構造（video_meta / knowledge_core / views）の哲学を踏襲しつつ、Web広告特有の「クリエイティブ」「LP」「パフォーマンス（実績）」を分離したトップレベル構造を採用する。

## トップレベル構造

\\\
{
  "asset_meta": { ... },        # 広告・媒体の基本情報
  "creative_core": { ... },      # クリエイティブ要素の詳細
  "landing_page": { ... },       # LP情報・訴求
  "performance": { ... },        # 実績データ・KPI
  "diagnostics": { ... },        # 分析結果・改善提案
  "views": { ... },              # UI表示用の整形済みサマリー
  "_metadata": { ... }           # トレーサビリティ情報
}
\\\

## 各セクション詳細

### 1. asset_meta

**役割**: 広告ID、プラットフォーム、キャンペーン名、期間等。「どの媒体の、いつの、何の広告か」を一意に特定するため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| ad_id | string | ✅ | 広告プラットフォーム上での一意ID | "ad_123456789" |
| platform | string | ✅ | 広告媒体（meta, google, tiktok等） | "meta" |
| campaign_name | string | ✅ | キャンペーン名 | "Q3_Retargeting_Sale" |
| adset_name | string | ✅ | 広告セット名 | "Website_Visitors_30d" |
| ad_name | string | ✅ | 広告名 | "Static_Discount_20off" |
| analysis_period | object | ✅ | 分析期間 | {"start": "2026-08-01", "end": "2026-08-31"} |

### 2. creative_core

**役割**: フォーマット、テキストコピ、フック（掴み）、訴求軸、CTA。広告の構成要素をLLMで分解・ラベル付けし、勝ちパターンの特徴量を抽出するため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| format | string | ✅ | クリエイティブのフォーマット | "static_image", "video" |
| primary_text | string | ✅ | プライマリテキスト（本文） | "夏の終わりの特別セール！今なら全品20%OFF。" |
| headline | string | ✅ | 見出し | "期間限定20%OFF" |
| call_to_action | string | ✅ | CTA（行動喚起） | "詳しくはこちら" |
| ai_labels | object | ❌ | LLM が生成したラベル | { "hook_type": "discount", "appeal_axis": "price", "target_audience": "cart_abandoners" } |
| platform_specific | object | ❌ | 媒体特有フィールド | { "placement": "fb_feed", "objective": "OUTCOME_SALES" } |

**ai_labels の例**:

\\\json
{
  "hook_type": "discount",           // 割引、ストーリー、UGC、実績等
  "appeal_axis": "price",            // 価格、品質、便利性、ステータス等
  "target_audience": "cart_abandoners", // ターゲット層の推定
  "emotion": "urgency",              // 緊急性、楽しさ、信頼等
  "tone": "casual"                   // カジュアル、フォーマル、高級感等
}
\\\

### 3. landing_page

**役割**: 遷移先URL、FV訴求、オファー内容、フォーム難易度。広告とLPのメッセージの一貫性（Message Match）を評価するため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| url | string | ✅ | LP遷移先URL | "https://example.com/sale" |
| fv_copy | string | ✅ | ファーストビュー訴求文 | "サマーセール開催中！" |
| offer | string | ✅ | オファー内容 | "20%割引クーポン" |
| form_difficulty | string | ❌ | フォーム難易度の推定 | "low", "medium", "high" |
| match_score_with_ad | number | ❌ | 広告とのメッセージマッチスコア（0-1） | 0.95 |

### 4. performance

**役割**: インプレッション、クリック数、CV、CPA、消化金額等の実績値。クリエイティブの良し悪しを実際の成果データで裏付けるため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| impressions | integer | ✅ | インプレッション数 | 150000 |
| clicks | integer | ✅ | クリック数 | 3000 |
| ctr | number | ✅ | クリックスルーレート（click / impressions） | 0.02 |
| spend | number | ✅ | 消化金額（円） | 50000 |
| conversions | integer | ✅ | コンバージョン数 | 50 |
| cpa | number | ✅ | 顧客獲得単価（spend / conversions） | 1000 |
| cvr | number | ✅ | コンバージョンレート（conversions / clicks） | 0.016 |
| reach | integer | ❌ | リーチ数 | 120000 |
| frequency | number | ❌ | 平均フリークエンシ | 1.25 |

### 5. diagnostics

**役割**: 広告疲弊スコア、LP一貫性スコア、改善推奨アクション。単なる集計ではなく、「次に何をすべきか」をシステムが提示するため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| creative_fatigue_risk | string | ✅ | クリエイティブ疲弊リスク判定 | "low", "medium", "high" |
| performance_status | string | ✅ | パフォーマンス総合評価 | "excellent", "good", "fair", "poor" |
| lp_message_match_risk | string | ❌ | LP一貫性リスク | "low", "medium", "high" |
| recommended_actions | array | ✅ | 改善提案（複数） | ["現在のクリエイティブは好調。予算の増額を検討。", "同様の価格訴求軸で動画フォーマットのテストを推奨。"] |

### 6. views

**役割**: ダッシュボード表示用の整形済み要約データ。UI層（Streamlit）での計算負荷を下げ、描画を高速化するため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| dashboard_summary | object | ✅ | ダッシュボード用サマリー | { "status_label": "Excellent", "key_metric_highlight": "CPAが目標より20%低い" } |
| performance_ranking | string | ❌ | ランキング内の相対位置 | "Top 10%" |
| trend_indicator | string | ❌ | トレンド（上昇/下降/横ばい） | "↑ +15%" |

### 7. _metadata

**役割**: 生成日時、データソース、AIモデルバージョン。トレーサビリティの確保とデバッグのため。

**フィールド定義**:

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| generated_at | string | ✅ | ISO 8601 形式の生成日時 | "2026-09-01T10:00:00Z" |
| data_source | string | ✅ | データソース | "meta_graph_api", "csv_import" |
| ai_model_version | string | ✅ | 使用したLLMモデル | "gemini-2.0", "gpt-4o" |
| version | string | ✅ | JSON スキーマバージョン | "1.0" |

## 拡張性設計

### 共通化（プラットフォーム非依存）
- \performance\ における標準KPI（imp, clicks, cv, spend）は全媒体で共通のキーを持つ
- \creative_core\ における抽象化された要素（hook, body, cta）は全媒体で共通

### 媒体特有の保持
- 各セクション内に \platform_specific\ オブジェクトを設け、Meta特有フィールド（例：placement、objective）を格納
- 共通ダッシュボードは標準キーを参照
- 特定媒体向けの詳細分析は特有キーを参照

## 完全な JSON サンプル

\\\json
{
  "asset_meta": {
    "ad_id": "ad_123456789",
    "platform": "meta",
    "campaign_name": "Q3_Retargeting_Sale",
    "adset_name": "Website_Visitors_30d",
    "ad_name": "Static_Discount_20off",
    "analysis_period": {
      "start": "2026-08-01",
      "end": "2026-08-31"
    }
  },
  "creative_core": {
    "format": "static_image",
    "primary_text": "夏の終わりの特別セール！今なら全品20%OFF。",
    "headline": "期間限定20%OFF",
    "call_to_action": "詳しくはこちら",
    "ai_labels": {
      "hook_type": "discount",
      "appeal_axis": "price",
      "target_audience": "cart_abandoners",
      "emotion": "urgency",
      "tone": "casual"
    },
    "platform_specific": {
      "placement": "fb_feed",
      "objective": "OUTCOME_SALES"
    }
  },
  "landing_page": {
    "url": "https://example.com/sale",
    "fv_copy": "サマーセール開催中！",
    "offer": "20%割引クーポン",
    "form_difficulty": "low",
    "match_score_with_ad": 0.95
  },
  "performance": {
    "impressions": 150000,
    "clicks": 3000,
    "ctr": 0.02,
    "spend": 50000,
    "conversions": 50,
    "cpa": 1000,
    "cvr": 0.016,
    "reach": 120000,
    "frequency": 1.25
  },
  "diagnostics": {
    "creative_fatigue_risk": "low",
    "performance_status": "excellent",
    "lp_message_match_risk": "low",
    "recommended_actions": [
      "現在のクリエイティブは好調。予算の増額を検討。",
      "同様の価格訴求軸で動画フォーマットのテストを推奨。"
    ]
  },
  "views": {
    "dashboard_summary": {
      "status_label": "Excellent",
      "key_metric_highlight": "CPAが目標より20%低い"
    },
    "performance_ranking": "Top 10%",
    "trend_indicator": "↑ +15%"
  },
  "_metadata": {
    "generated_at": "2026-09-01T10:00:00Z",
    "data_source": "meta_graph_api",
    "ai_model_version": "gemini-2.0",
    "version": "1.0"
  }
}
\\\
"@ | Out-File -Encoding UTF8 docs/specs/ad_insight_json_schema_draft.md

Write-Host "✅ docs/specs/ad_insight_json_schema_draft.md を作成しました"

# ===== 3. docs/architecture/system_overview.md =====
@"
# システムアーキテクチャ概要 - Ad-Insight-Spec

## システムフロー

\\\
[1. データ取込層]
   ↓
Meta Ads API / CSV Export / スクレイピング
   ↓ (生データ)
   ↓
[2. 正規化・AI解析層]
   ↓
LLM (Gemini/OpenAI) でクリエイティブ要素分解・タグ付け
   ↓
[3. JSON生成層]
   ↓
ad_insight_spec.json （本スキーマ）の出力
   ↓
[4. 分析・レポート層]
   ↓
├─ Streamlit ダッシュボード（インタラクティブ分析）
├─ Static HTML/PDF レポート生成
└─ PostgreSQL Repository （データ永続化）
   ↓
[5. AI解説層]
   ↓
Narrative Engine：実績データとタグに基づく具体的な改善提案の自動言語化
\\\

## レイヤー別責務

### 1. データ取込層 (Ingestion)

**責務**: Meta Ads API、CSV、スクレイピングから生データを取得し、正規化前の形式で一時保存する。

**主要コンポーネント**:
- Meta Graph API クライアント
- CSV インポーター
- スクレイピングモジュール（LP自動抽出）

**出力**: Raw JSON または中間形式

### 2. 正規化・AI解析層 (Normalization & Analysis)

**責務**: 生データを\d_insight_spec\の形式に正規化し、LLMを用いてクリエイティブ要素を分解・ラベル付けする。

**主要コンポーネント**:
- Converter/Normalizer
- LLM Prompt Manager (Gemini/OpenAI 連携)
- Creative Element Extractor (Hook, Body, CTA 分解)
- Landing Page Matcher (広告とLPの関連付け)

**処理フロー**:
1. Meta API データ → フィールドマッピング
2. 画像/動画 → LLM で要素分解（OCR含む）
3. LP スクレイピング → テキスト抽出
4. メッセージマッチスコア計算

**出力**: \d_insight_spec.json\

### 3. JSON生成・永続化層 (Persistence)

**責務**: 正規化されたJSONを PostgreSQL に保存し、バージョン管理する。

**主要コンポーネント**:
- SQLAlchemy ORM モデル
- Repository パターン（CRUD操作）
- Alembic マイグレーション

**テーブル例**:
- \ds\ - 広告マスター
- \d_insights\ - JSON ペイロード（JSONB）
- \d_analysis_history\ - 分析履歴（トレーサビリティ）

### 4. 分析・レポート層 (Analytics & Reporting)

#### 4a. Streamlit ダッシュボード

**責務**: インタラクティブな分析画面をユーザーに提供する。

**主要タブ**:
- **全体パフォーマンス**: CPA/CVR マッピング、KPI サマリー
- **クリエイティブ分析**: フック・訴求軸・CTAの分解、パターン検出
- **LP一貫性診断**: メッセージズレ警告、フォーム最適化提案
- **AI改善提案**: Narrative Engine から出力された具体的なアクション

**技術**:
- Streamlit フレームワーク
- キャッシング機構（venv内のメモリ/Redis）
- インタラクティブフィルタリング

#### 4b. HTML/PDF レポート生成

**責務**: 経営陣向けの1枚ペラエグゼクティブサマリーを生成する。

**出力形式**:
- HTML（inline CSS）
- PDF（ReportLab）

**含有情報**:
- CPA、CVR、消化金額 のサマリー
- AI による改善アクション
- 過去比較チャート

### 5. AI解説層 (Narrative Engine)

**責務**: 実績データとタグに基づき、マーケター向けの具体的な改善提案を自動生成する。

**入力**: \performance\, \diagnostics\, \i_labels\

**プロンプトテンプレート**:
\\\
{ad_name} は {appeal_axis} を訴求軸とした {format} クリエイティブです。
{analysis_period} の実績は、CPA {cpa}、CVR {cvr}% です。

診断結果：{creative_fatigue_risk} レベルのクリエイティブ疲弊リスク
改善提案：...
\\\

**出力**: 日本語テキスト形式の改善提案

## 技術スタック詳細

### Backend

| レイヤー | 技術 | 用途 |
|---------|------|------|
| API Framework | FastAPI | REST API エンドポイント |
| Database | PostgreSQL 15+ | 永続データストア |
| ORM | SQLAlchemy | テーブルモデル定義 |
| Migration | Alembic | スキーマ管理 |
| LLM Client | Google Generative AI SDK / OpenAI | AI解析呼び出し |
| Data Validation | Pydantic | リクエスト/レスポンス検証 |
| Async | asyncio + HTTPX | 非同期I/O |

### Frontend

| レイヤー | 技術 | 用途 |
|---------|------|------|
| Framework | Vue.js 3 | UI フレームワーク |
| State Management | Pinia | 状態管理ストア |
| Build Tool | Vite | 高速ビルド |
| HTTP Client | Axios | API通信 |
| Styling | Tailwind CSS | スタイリング（予定） |
| Chart Library | Chart.js / ECharts | グラフ表示 |

### Infrastructure

| コンポーネント | 技術 | 用途 |
|-------------|------|------|
| Containerization | Docker | 環境の一元化 |
| Orchestration | docker-compose | ローカル開発 |
| CI/CD | GitHub Actions | 自動テスト・デプロイ |
| Hosting | Cloud Run / EC2（予定） | 本番デプロイ |

## VIS資産の流用

### そのまま流用

- **HTML/Text レポート生成フレームワーク** (converter/report_generator.py など)
  - テンプレート内容を「動画」から「広告クリエイティブ・LP実績」向けに差し替え

- **Streamlit アプリケーション骨格** (streamlit_app/app.py)
  - UIレイアウト・キャッシュ機構・ページ構成をそのまま流用

- **LLM クライアント基盤** (Gemini/OpenAI 連携)
  - プロンプト内容をWeb広告マーケター視点に全面改修

### 調整必須

- **JSONスキーマ** (insight_spec → 新スキーマ)
  - 動画特有フィールド削除、広告・LP・パフォーマンス構造へ転換

- **分析・スコアリングロジック**
  - 動画の「エンゲージメント推定」→ 広告の「実績CPA/CVR」に変更

- **Narrative Engine プロンプト**
  - 「動画の視聴体験」→ 「広告の効果改善提案」へ転換

### 破棄・新規実装

- **YouTube API 特化モジュール** (youtube_metadata_service.py など)

- **動画のミリ秒単位処理に依存したロジック**

- **Meta Ads API 連携** → 新規実装
