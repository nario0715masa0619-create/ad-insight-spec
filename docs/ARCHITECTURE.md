# アーキテクチャ設計

Ad-Insight-Spec は、広告のクリエイティブアセットを分析し、統一されたフォーマット (`AdInsightSpec`) として出力・管理するシステムです。

## 1. システム全体構成

### データフロー

1. **入力**: ユーザーが API または Streamlit UI 経由でファイルをアップロード
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
- `analyze_creative_improvements` メソッド：改善コメント生成専用
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

**複合キー戦略:**
- Primary Key: `(asset_id, version)`
- 同一 `asset_id` への再分析時、バージョンは削除済みを含む全履歴の `max+1` を採番して保存します。
- 例: asset_id "asset_image_abc123" の履歴 v1, v2 が存在 → 新規分析時は v3 として保存。

---

## 4. API / UI インターフェース（現行実装）

### FastAPI エンドポイント
正式な API パスは以下の通り統一されています。
- `POST /api/v1/specs/analyze`: 分析実行
- `GET /api/v1/specs`: 分析結果一覧取得
- `GET /api/v1/specs/{asset_id}`: 分析結果詳細取得
- `DELETE /api/v1/specs/{asset_id}`: 分析結果の論理削除

### Streamlit UI
`frontend/streamlit_app.py` により、ブラウザ上で手軽に以下の操作が可能です。
- クリエイティブのアップロードとモード選択による分析
- 過去の分析結果のリスト表示
- 結果 JSON の詳細確認
- 分析結果の削除（論理削除）

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
