# Incident Report: OpenAI API LLM Analysis Not Triggered (2026-07-01)

## 障害概要
- **発生日時:** 2026年07月01日
- **対象環境:** GCP 本番環境 (`instance-20260626-073827`)
- **症状:** Streamlit UI 上で分析を実行しても LLM 処理が発火せず、空の結果またはエラーになる。また、OpenAI クライアント初期化時に `proxies` 引数エラー、および Pydantic オブジェクトにおける `model_dump` メソッド不足のエラーが発生。
- **影響範囲:** LLM による分析・改善コメント生成フロー全体

## 根本原因
1. **APIキー読み込みロジックの不備:**
   `backend/app/services/llm_service.py` のモジュールトップレベルにて `OPENAI_API_KEY` を静的に取得 (`os.getenv`) しており、GCP 環境における `.env` の配置パス (`/opt/ad-insight-spec/backend/.env`) がコードに定義されていなかったため、API キーが未設定のまま分析がスキップ (non-fatal) されていた。
2. **OpenAI SDK と httpx のバージョン競合:**
   環境構築時に最新の `httpx 0.28.1` が入り、OpenAI 1.3.0 内部の `proxies` 渡し処理と互換性が無くなりエラーが発生。
3. **Pydantic v1/v2 混在によるダンプエラー:**
   Pydantic v2 ランタイム下で、v1 API (`.dict()`) にしか対応していないスキーマに対して `.model_dump()` が暗黙に呼ばれる、または `.dict()` がハードコードされていることで互換性エラーが発生。

## 対応内容と修正ファイル
- **対応時間:** 約 3 時間（調査・改修・テスト）
- **対応者:** Nario / Antigravity AI
- **修正内容:**
  - `config.py`: 環境変数の探索パスに `/opt/ad-insight-spec/backend/.env` を追加。
  - `llm_service.py`: モジュールトップでの静的ロードを廃止し、`get_settings()` を用いたメソッド内での動的ロードへリファクタリング。
  - `llm_service.py`: OpenAI クライアント初期化時に `httpx.Client(proxy=...)` を用いるよう明示的実装に変更。
  - `llm_service.py`, `analysis_orchestrator.py`: Pydantic の `model_dump()` と `dict()` の両方に対応するセーフなヘルパー関数を導入。

### 修正ファイル一覧
- `backend/app/config.py`
- `backend/app/services/llm_service.py`
- `backend/app/services/analysis_orchestrator.py`
- `frontend/streamlit_app.py` （UIログの強化）
- `docs/DEPLOYMENT.md` （GCP FW設定手順の追記）

## 実施したコミット一覧（mainへ直接 push）
- `e25980e`: refactor: dynamically load API keys via get_settings instead of global variables
- `2eadf84`: fix: make all pydantic serialization calls compatible with v1 and v2 using _dump_model helper
- `e069ecf`: fix: make CreativeCoreSchema validation and dumping compatible with both Pydantic v1 and v2
- `eb97359`: fix: resolve OpenAI client proxies parameter issue and update Streamlit logs

## Smoke Test 結果
- [x] FastAPI サーバーの正常起動確認
- [x] Streamlit UI (ポート 8501) への接続と「分析中...」リアルタイムログの表示確認
- [x] 環境変数 (`OPENAI_API_KEY`) の正常ロードおよび OpenAI API エンドポイントへの呼び出し成功
- [x] LLM レスポンスの正常パース・UI 上への結果描画
