# アーキテクチャ設計

CampaignPilot（旧: Ad-Insight-Spec / AIS）は、広告分析において人間が行っている「構造の読み解き」「評価根拠の整理」「改善提案の言語化」を、入力された広告素材・LP・KPIから自動生成された診断レポートに置き換えることを目的とするシステムです。
広告改善の意思決定や分析実務を担うマーケティング担当者を主要利用者として想定し、制作会社や代理店においても自前分析を効率化するための利用を想定しています。

本システムは、以下の広告分析タスクを自動化対象とします。
- 広告素材の構造分解、訴求・トーン・視覚要素の整理
- 広告とLPの整合性評価、および必要に応じたKPI解釈
- 根拠付き診断と改善アクションの言語化

## 1. システム全体構成

### 基本利用フローと対象スコープ
本システムの基本利用フローは **「素材投入 → 診断生成 → 結果確認」** であり、保存済み診断レコードの参照・比較は補助機能として扱います。
また、本システムは自社広告だけでなく、競合広告やトレンド広告も同一スキーマで診断できますが、競合候補の探索・選定自体は外部ツールやユーザーの判断に委ねる（本システムの責務外とする）設計です。

### データフロー

1. **入力**: ユーザーが API または UI 経由で分析対象のファイルを投入
2. **メタデータ抽出**: ファイルハッシュに基づく一意の `asset_id` 生成および基本メタデータ抽出
3. **コンテンツ解析**:
   - 画像 / 動画フレーム抽出
   - LP スクレイピング
   - OCR テキスト抽出 (Tesseract)
4. **LLM 解析**: コンテンツ情報（画像、OCRテキスト、LPテキスト）を統合し、LLM がクリエイティブ特性やトーン、メッセージを定性分析
5. **変換**: 分析結果を `AdInsightSpec v0.2` の JSON 構造に変換
6. **保存**: SQLite データベースに履歴 (`version`) 付きで保存

### 3 つの入力モード
1. **`file_only`**: クリエイティブ（画像/動画）単体での分析。
2. **`file_plus_lp`**: クリエイティブ ＋ ランディングページ (LP) の分析。LP のメッセージとの一貫性を評価します。
3. **`file_plus_lp_plus_manual_kpi`**: KPI情報を含め、パフォーマンスとクリエイティブ特性の相関を分析します。

---

## 2. 7 つのコアサービス（現行実装）

バックエンドは、単一責任の原則に基づき、以下の 7 つのコアサービスで構成されています。

### IngestionService
ファイルのアップロード処理と形式（画像、動画等）の判定を行います。

### MetadataService
ファイルの一意な識別子 (`asset_id`) の生成と、ファイルメタデータ（解像度、フォーマット、サイズ等）の抽出を行います。

### VideoService
FFmpeg/OpenCV を使用し、動画ファイルから主要なフレーム（先頭・中間・末尾など）を画像として抽出します。

### LPService
BeautifulSoup などを利用し、指定された LP の URL からファーストビュー (FV) のテキストや構造情報をスクレイピングします。

### OCRService
Tesseract-OCR を使用し、画像または動画フレームからテキスト情報を抽出します。文字が読み取れなかった場合も処理を継続する Fail-Soft 仕様を実装しています。

### LLMService（デュアル実装）

**現行実装:**
- **GPT-4o（本命）**: 主分析エンジン。高い推論能力でクリエイティブ特性を構造化します。
- **Gemini 2.0 Flash（現行比較対象）**: 比較分析用途。

**機能:**
- `visuals` / `tone` / `ai_labels` などを分析
- 自動再試行（最大 3 回）による安定性確保
- Pydantic による JSON Schema の固定化・バリデーション

**注記:** Gemini 2.0 Flash は将来的に他のモデル（Claude 等）への差し替え候補です。

### ConverterService
各 Service から出力された解析結果を集約し、最終的な `AdInsightSpec v0.2` 準拠の JSON ディクショナリに変換します。

### MetaAdsCsvService（Phase 1: Meta Ads CSV インポート）
Meta Ads Manager からエクスポートされたCSVを、列の並べ替えや事前整形なしで受け取れるようにするサービスです。
`AnalysisOrchestrator._step_load_kpi` が `kpi_file` の拡張子（`.csv` / `.json`）で処理を振り分けます（既存の手入力KPI(JSON)フローには影響しません）。

- 日本語/英語の主要な列名ゆれを吸収し、内部フィールド（impressions/clicks/spend/conversions等）へマッピング
- キャンペーン/広告セット/広告のいずれの粒度かを列の有無から判定し、`asset_meta.kpi_granularity` に記録
- 複数行（日別内訳等）は主要指標を合算し、分析期間は最小開始日〜最大終了日を採用
- 必須列（インプレッション・クリック）が無い/数値として読めない場合は `MetaAdsCsvError` を送出し、API層（`specs.py`）が 422 + 具体的な案内文で応答

詳細は [docs/META_ADS_CSV_IMPORT.md](META_ADS_CSV_IMPORT.md) を参照してください。

### P0: 改善文章品質向上

**スキーマ層**
- `ImprovementComment`: 根拠・アクション・優先度を構造化
- `LLMImprovementValidationError`: fail-soft 時のエラー構造

**バリデーション層（llm_validator_service.py）**
- 抽象語検知：「訴求力」「見栄え」など定義済みキーワードを検出
- 根拠欠落検知：evidence フィールドが空でないか確認
- 対象不明検知：target_scope が曖昧な表現（「全体」「複数」等）でないか確認
- 矛盾検知：improvement_type と evidence が矛盾していないか確認
- fail-soft: バリデーション失敗時も構造化エラーで安全に応答

**LLM統合層（llm_service.py）**
- `analyze_creative_improvements` メソッド：改善コメント生成専用（`diagnostics.improvements`）
- `generate_decision_support` メソッド：強み・弱み・改善提案の意思決定支援ブロック生成専用（`diagnostics.decision_support`、improvementsとは独立したfail-soft呼び出し）
- 3回再試行ロジック：API エラー時に自動リトライ
- timeout 60秒、rate-limit 対応

**Streamlit UI統合**
- 「✨ 改善提案」セクション：上位3件を優先度ラベル付きで表示
- 詳細展開：`st.expander` で根拠・アクションを表示
- fail-soft 警告：`st.warning` で安全に表示

---

## 3. データベース設計

### 現行実装（SQLite）

#### AdInsight テーブル設計

| カラム | 型 | 説明 |
|--------|-----|------|
| asset_id | VARCHAR(64) | SHA-256 ハッシュベース識別子 |
| version | INT | 同一 asset_id への再分析時のバージョン番号 |
| format | VARCHAR(10) | "json" 固定 |
| spec_data | JSON/TEXT | 完全な AdInsightSpec |
| is_deleted | BOOLEAN | 論理削除フラグ |
| created_at | TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | 更新日時 |
| company_id | INT (nullable, FK) | 招待制モニターベータ導入以降、作成した会社を記録（データ分離・月次クレジット利用量カウントに使用。既存レコードはNULL） |
| created_by_user_id | INT (nullable, FK) | 作成したモニターユーザー |

#### モニターベータ用テーブル（`monitor_companies` / `monitor_users` / `monitor_sessions` / `credit_usage_logs`）

招待制モニターベータ公開のために追加したテーブル群です。詳細なカラム定義は
`backend/app/models/beta_access.py`、運用手順は
[MONITOR_ACCOUNT_MANAGEMENT.md](./MONITOR_ACCOUNT_MANAGEMENT.md) を参照してください。
利用上限は「月◯件」ではなく「月次クレジット」方式（詳細:
[MONITOR_BETA_OPERATION.md](./MONITOR_BETA_OPERATION.md)、設計背景:
[クレジット課金設計案](./campaignpilot_credit_billing_design.md)）。

- `monitor_companies`: モニター企業（テナント）。`monthly_credit_limit`（月次クレジット上限）を保持。
- `monitor_users`: 招待されたユーザー。自由登録経路は存在せず、管理者/CLIのみが作成可能。
- `credit_usage_logs`: クレジット消費ログ。分析が成功した時のみ行が作られる
  （「実行前チェック→成功時のみ消費確定」方式のため、失敗した分析は一切現れない）。
  当月の利用量はこのテーブルを都度集計して求め、集計用のスナップショットは持たない。
- `monitor_sessions`: サーバー保持のログインセッション（署名付きトークンではなくDB行として管理し、
  停止時に即時失効できるようにしている）。

**複合キー戦略:**
- Primary Key: `(asset_id, version)`
- 同一 `asset_id` への再分析時、バージョンは削除済みを含む全履歴の `max+1` を採番して保存します。
- 例: asset_id "asset_image_abc123" の履歴 v1, v2 が存在 → 新規分析時は v3 として保存。

---

## 4. API / UI インターフェース（現行実装）

### FastAPI エンドポイント
正式な API パスは以下の通り統一されています。招待制モニターベータ導入以降、
`/api/v1/specs/*` と `/api/v1/verification/*` は全てログイン必須です
（`Authorization: Bearer <session_token>` ヘッダー、`app/api/deps.py::get_current_user`）。
- `POST /api/v1/specs/analyze`: 分析実行（ログイン中ユーザーの会社の月次クレジット残量が
  この分析の消費量以上ある場合のみ実行。成功時のみクレジット消費が確定する）
- `GET /api/v1/specs`: 分析結果一覧取得（ログイン中ユーザーの所属会社が所有するレコードのみ）
- `GET /api/v1/specs/{asset_id}`: 分析結果詳細取得（他社所有のasset_idは404）
- `DELETE /api/v1/specs/{asset_id}`: 分析結果の論理削除（他社所有のasset_idは404）
- `POST /api/v1/auth/login` / `POST /api/v1/auth/logout` / `GET /api/v1/auth/me`: 招待制ログイン
- `/api/v1/admin/*`: モニター企業・ユーザー管理（`is_admin=true` のユーザーのみ）

詳細は本ドキュメントのデータベース設計セクション、および
[MONITOR_BETA_OPERATION.md](./MONITOR_BETA_OPERATION.md) を参照してください。

### Streamlit UI
`frontend/streamlit_app.py` による UI は、「一覧/ダッシュボード」ではなく **「分析開始（アップロード）」を起動直後の第一画面** とし、以下の構成順序を推奨します。

1. **分析（アップロード）**: 広告素材を投入し、新規診断を実行
2. **分析結果**: 分析完了直後に表示される、診断詳細の確認画面（独立タブではなく結果画面として扱う）
3. **保存済み結果**: 過去に生成された診断結果の参照画面
4. **ダッシュボード**: 全体の傾向把握（必要に応じて）

※ 詳細な履歴管理や「Delete（論理削除）」は主要ナビゲーションから外し、補助的な裏側機能として位置づけます。

---

## 5. JSON Schema (AdInsightSpec v0.2)

`backend/app/schemas/ad_insight.py` 内に定義されており、Pydantic を用いて入力と出力の厳密な型・構造バリデーションを実施しています。
主なセクションは以下の通りです。
- `input_metadata`: 解析条件や入力元情報
- `asset_meta`: 識別子、メタデータ
- `creative_core`: 抽出したフォーマット、画像特性、テキスト、トーン、AI ラベル、OCR テキスト
- `landing_page`: LP との整合性評価
- `performance`: KPI 情報
- `diagnostics`: アセットの健全性診断
- `views`: フロントエンド表示用サマリー
- `_metadata`: システム処理情報

---

## 6. テスト戦略（現行実装）

- `pytest` ベースの単体テストおよび E2E テストを実装。
- 各サービスの機能単位テスト (`tests/`) と、一連の API フローを通しでテストする E2E テスト (`scripts/e2e_test_phase2c2.py`) により品質を担保。
- OCRの Fail-Soft 処理やデータベースのバージョン・論理削除挙動の検証も自動化。

---

## 7. 依存関係・技術スタック（現行実装）

- **言語**: Python 3.13+
- **API フレームワーク**: FastAPI
- **フロントエンド**: Streamlit
- **データベース**: SQLite
- **LLM クライアント**: OpenAI (`openai`), Google Generative AI (`google-generativeai`)
- **バリデーション**: Pydantic
- **OCR Engine**: Tesseract (`pytesseract`)
- **メディア処理**: OpenCV (`opencv-python`), Pillow (`Pillow`)

---

## 8. 今後の拡張予定

現在のアーキテクチャを踏まえ、将来的には以下の拡張を想定しています。

1. **PostgreSQL 移行**: スケーラビリティと堅牢なトランザクション管理のため。
2. **非同期処理の導入**: 分析時間の長いタスク（LLM や動画処理）を Celery や Redis を使った非同期ワーカーに分離。
3. **Meta / Google Ads API 連携**: アセットの実パフォーマンスデータ (KPI) の自動取得。
4. **キャッシング**: 重複ファイル解析をスキップするためのレスポンスのキャッシュ処理。
