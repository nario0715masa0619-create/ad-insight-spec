# Ad-Insight-Spec

Ad-Insight-Spec は、広告クリエイティブ（画像・動画）とランディングページ（LP）から抽出した情報を元に、LLM を用いて広告の定性・定量分析を行い、統合された JSON 仕様 (AdInsightSpec v0.2) に変換して管理するシステムです。

## クイックスタート

### 1. インストール
`ash
git clone https://github.com/nario0715masa0619-create/ad-insight-spec.git
cd ad-insight-spec/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
`

### 2. 環境変数設定
ackend/.env を作成し、以下を設定します。
`env
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
LLM_MODEL=gpt  # または gemini
`

### 3. アプリケーション起動
**バックエンド (FastAPI)**
`ash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
`

**フロントエンド (Streamlit UI)**
別のターミナルを開き、ルートディレクトリから実行します。
`ash
streamlit run frontend/streamlit_app.py
`

## 全体構成図
- **7つのコアサービス**: Ingestion, Metadata, Video, LP, OCR, LLM, Converter
- **DB (SQLite)**: 分析結果と履歴（バージョン）を管理
- **UI (Streamlit)**: 簡易的なユーザーインターフェースによる動作確認

## Phase 完了状態一覧

| Phase | タスク | ステータス |
|-------|--------|------------|
| Phase 1 | 基盤構築（FastAPI, SQLite, SQLiteRepository） | ✅ 完了 |
| Phase 2a | 統合スキーマ v0.2 と API 基本設計 (CRUD) | ✅ 完了 |
| Phase 2b | E2E 分析パイプラインと Streamlit UI | ✅ 完了 |
| Phase 2c-1 | LLMService 統合 (GPT/Gemini デュアル実装) | ✅ 完了 |
| Phase 2c-2 | OCRService 統合 (Tesseract, 画像/動画フレーム対応) | ✅ 完了 |
| Phase 2c-3 | AnalysisOrchestrator と ConverterService の完成 | ✅ 完了 |

## 主要機能

- **3つの入力モード**:
  1. ile_only: クリエイティブ（画像/動画）単体での分析
  2. ile_plus_lp: クリエイティブ ＋ LP での分析（未実装項目あり）
  3. ile_plus_lp_plus_manual_kpi: KPI情報を含めたフル分析
- **4つのエンドポイント**: nalyze, GET, GET by ID, DELETE
- **Streamlit UI**: ファイルアップロードから分析、結果の一覧表示、詳細確認までをブラウザ上で実行可能

## API エンドポイント

- **POST /api/v1/specs/analyze**
  - ファイルの分析を実行し、結果を DB に保存後、JSON を返却
- **GET /api/v1/specs**
  - 分析結果の一覧を取得（ページング対応、論理削除済みは除外）
- **GET /api/v1/specs/{asset_id}**
  - 指定した sset_id の分析結果を取得（?version= で指定可能）
- **DELETE /api/v1/specs/{asset_id}**
  - 指定した sset_id の全バージョンを論理削除

## 現状の制約・既知の制限
- **非同期処理の未対応**: 長時間の LLM 処理や動画処理においてタイムアウトのリスクがあります（今後の拡張で Celery 等を導入予定）。
- **Tesseract OCR の依存**: OCR の利用にはホストマシンへの Tesseract-OCR 本体のインストールが必須です。
- **LP 解析の制限**: 簡易的なスクレイピングのみ実装されており、動的ページには完全対応していません。

## 参考・次ステップ
詳細なシステム構成や運用手順については、以下のドキュメントを参照してください。
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): システム設計・データベース設計
- [OPERATIONS.md](docs/OPERATIONS.md): 開発・本番環境での運用ガイド