# 運用・オペレーションガイド

本ドキュメントでは、CampaignPilot（旧: Ad-Insight-Spec）の開発環境と本番環境におけるセットアップ、運用手順、およびトラブルシューティングについて解説します。

---

## 1. 開発環境前提

### 推奨スペック
- **OS**: Windows, macOS, Linux いずれでも動作可能
- **CPU**: 最低 2 コア
- **メモリ**: 8GB 以上推奨（動画処理を行う場合はより多くのメモリが必要です）

### インストール手順

1. **Python 環境の構築**
   ```bash
   git clone https://github.com/nario0715masa0619-create/ad-insight-spec.git
   cd ad-insight-spec/backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **外部依存ツールのインストール**
   - **Tesseract-OCR**: 
     - Windows: インストーラーをダウンロードし、環境変数 `TESSERACT_PATH` にパスを設定してください。
     - macOS: `brew install tesseract`
     - Linux: `sudo apt-get install tesseract-ocr`
   - **FFmpeg** (動画フレーム抽出用):
     - OS パッケージマネージャ経由でインストールし、システムパスが通っていることを確認してください。

### 開発用 .env 設定
`backend/.env` を作成し、以下を設定します。
```env
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
LLM_MODEL=gpt
# TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe  # Windows の場合のみ
```

### 開発起動手順
- **バックエンド**
  ```bash
  cd backend
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  ```
- **フロントエンド**
  ```bash
  streamlit run frontend/streamlit_app.py
  ```

### 開発テスト実行
```bash
cd backend
python -m pytest tests/ -v
# または E2E テスト
python ../scripts/e2e_test_phase2c2.py
```

### 開発環境での注意点
- `uvicorn --reload` を使用すると、コード変更時に自動的にサーバーが再起動します。
- SQLite DB (`ad_insight.db`) はローカルにファイルとして生成されます。

---

## 2. 本番環境前提

### 推奨スペック
- **OS**: Linux (Ubuntu 22.04 LTS 等) 推奨
- **CPU**: 4 コア以上
- **メモリ**: 16GB 以上（同時リクエスト数や動画処理頻度に依存）

### 本番環境チェックリスト（2.1～2.10）

1. **インフラストラクチャ**: リバースプロキシでの SSL/TLS 通信の適用、不要なポートのファイアウォール遮断。
2. **ツール・依存関係**: Tesseract, FFmpeg をシステムパッケージとして本番サーバーにインストール。
3. **データベース**: 本番稼働時は SQLite ではなく **PostgreSQL** への移行と定期バックアップ戦略の導入を推奨。
4. **API キー・シークレット管理**: `.env` での直接管理は避け、AWS Secrets Manager 等の機密情報管理サービスを推奨。
5. **アプリケーション設定**: デバッグモード無効化 (`DEBUG=False`)、ログレベルの適切な設定 (`LOG_LEVEL=INFO`)。
6. **ロギング・監視**: アプリケーションログの CloudWatch または ELK スタックへの転送とモニタリング。
7. **デプロイ・起動**: Gunicorn 等の WSGI/ASGI サーバーを使用し、Nginx などを前段に置く。Systemd 等での自動再起動設定。
8. **セキュリティ**: CORS の適切な制限設定、API レート制限の設定。
9. **バックアップ・災害対応**: DB 定期バックアップおよびスナップショットの取得。
10. **パフォーマンス**: タイムアウト設定、非同期タスクキュー（Celery 等）の導入、コネクションプーリングの設定。

### 本番環境用 .env 例
```env
ENVIRONMENT=production
DEBUG=False
LOG_LEVEL=INFO
DATABASE_URL=postgresql://user:password@host/dbname
OPENAI_API_KEY=...
LLM_MODEL=gpt
```

### 本番環境起動
Gunicorn + Uvicorn 構成での起動例:
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 3. 共通：テスト実行
本番デプロイ前には必ず以下のテストを実行し、すべて通過することを確認してください。
- ユニットテスト: `pytest tests/`
- E2E テスト: 定義されたシナリオスクリプトを実行し、システムの結合状態を確認。

---

## 4. 共通：トラブルシューティング

- **Q: LLM からのレスポンスがエラーになる**
  - A: API キーが正しく設定されているか、または API の利用限度額に達していないか確認してください。
- **Q: OCR のテキスト抽出が空になる**
  - A: Tesseract のインストールパスが間違っていないか、また言語データ (eng+jpn) がインストールされているか確認してください。Fail-Soft によりシステムは停止しません。
- **Q: DB ロックエラーが発生する (SQLite)**
  - A: 並行アクセスにより SQLite がロックされることがあります。本番環境では PostgreSQL への移行を検討してください。

---

## 5. 共通：ログ出力設定
標準の Python `logging` を使用し、処理のステップごとに情報を出力しています。
本番では `logger.error` を中心に監視アラートを設定することを推奨します。

---

## 6. 本番環境への移行チェックリスト
- [ ] Tesseract, FFmpeg パッケージのインストール
- [ ] リバースプロキシ / SSL 化の完了
- [ ] シークレット情報のセキュアな配置
- [ ] PostgreSQL へのデータ移行（今後の拡張）
- [ ] 自動起動（systemd）と Gunicorn サーバー設定の完了
- [ ] ヘルスチェック・ログ監視の設定確認

---

## 7. P0 改善文章品質向上の運用影響

### LLM API コストとパフォーマンス
- **コスト増加**: P0実装により、従来の「分析」に加え「改善コメント生成」の追加API呼び出しが発生します。呼び出し回数が1アセットあたり2回になるため、単価×2の見積もりが必要です。
- **分析時間の増加**: OCR処理や追加のLLM呼び出しにより、分析完了までの時間が数秒増加します。UI上は「分析実行中」のインジケーターで待機させます。

### 改善コメント表示機能の運用
- **UI 表示フロー**:
  1. 分析が完了すると、UI の「✨ 改善提案」セクションに上位3件の改善コメントが自動展開されます。
  2. 優先度ラベル（🔴P0/🟠P1等）と1行要約により、ユーザーは「どこを直すべきか」を瞬時に判断できます。
  3. 必要に応じて「詳細を見る」を展開し、根拠と具体的なアクションを確認します。
  ※このフローにより、ユーザーは3分以内に次のアクションを決定できます。

### fail-soft 対応と障害時の手順
- **LLM API キー無効化・エラー時の動作**:
  - APIキーの無効化やレート制限超過により改善コメント生成が失敗した場合、バックエンドは `500 Internal Server Error` にならず、`diagnostics.improvements` を `None` として代替応答を返します（fail-soft）。
  - UI 上では既存の分析結果（メタデータやCreativeCore等）を破壊することなく、該当セクションのみに `st.warning` で「⚠️ 改善コメント生成に失敗しました」と警告が表示されます。
- **ユーザーへの周知**:
  - fail-soft発生時は、システム管理者へJSON構造化ログのエラー通知（`request_id` 付き）が飛びます。
  - ユーザーには「一時的な生成エラーであり、他の分析結果は正常に保存されています」と案内してください。
- **障害時確認手順**:
  1. `/health` エンドポイントを叩き、FastAPI と DB 接続の基本状態を確認します。
  2. ログ監視ツールで `error_code: VALIDATION_FAILED` 等の JSON 構造化ログを `request_id` や `trace_id` で検索・解読します。
  3. LLM API エラーの場合: API キーの有効性、レート制限、またはバックエンドの再試行設定を確認します。
  4. OCR エラーの場合: Tesseract の状態やシステムリソースを確認します。

---

## 8. 障害診断の最速フロー（Phase 1 診断チェックリスト）

本番環境（特にGCP等）で予期せぬ挙動（例：分析がスキップされる、UIが更新されない等）が発生した場合、以下の30分以内チェックリストに沿って迅速に原因を切り分けます。

### 30分以内チェックリスト
- [ ] **1. FastAPI プロセス環境確認 (5分)**: FastAPIが意図した環境変数（特に `.env` パス）で起動しているか確認する。
- [ ] **2. systemd サービス状態確認 (5分)**: サービスが Active になっているか、エラーで再起動を繰り返していないか確認する。
- [ ] **3. LLM 呼び出しログ確認 (10分)**: `OPENAI_API_KEY` の読み込みエラーや Pydantic 関連のエラーが出ていないか確認する。
- [ ] **4. Streamlit UI 動作確認 (10分)**: ネットワーク接続や UI のリアルタイムログから処理の停止箇所を特定する。

### 実環境でのデバッグコマンド集

#### systemd 環境変数・状態確認コマンド
```bash
# サービスのステータスと直近のログを確認
sudo systemctl status ad-insight-fastapi.service

# systemd サービスに渡されている環境変数を確認
sudo systemctl show ad-insight-fastapi.service --property=Environment,EnvironmentFile
```

#### FastAPI プロセス環境確認コマンド
```bash
# FastAPI (uvicorn) プロセスの PID を特定
pgrep -f uvicorn

# 特定した PID (例: 1234) の環境変数を出力（APIキー等を安全に確認）
sudo cat /proc/1234/environ | tr '\0' '\n' | grep -E "OPENAI|GEMINI|env"
```

#### LLM 呼び出し確認ログコマンド
```bash
# FastAPI のエラーログから LLM 関連のスキップや例外を抽出
cat /tmp/fastapi.log | grep -iE "llm|openai|validation|error"
```

---

## 9. AIS 1クリック運用ツール（Windows）

本番 GCP VM（`instance-20260626-073827` / `asia-northeast1-a`）上の FastAPI（`ad-insight-fastapi.service`）・Streamlit（`ad-insight-streamlit.service`）を、Windows端末からダブルクリックのみで操作するための最小構成ツールです。SSHは `gcloud compute ssh` の鍵認証をそのまま利用し、新規の鍵・PAT・sudoers設定は追加していません。

### 9.1 配置場所
- **Windows側（利用者が操作するファイル）**: `D:\ClaudeCodeWork\AIS\`
  - `AIS_Open.bat`
  - `AIS_Status.bat`
  - `AIS_Restart.bat`
- **VM側補助スクリプト（bat から SSH 経由で呼び出す実処理、gitリポジトリ管理外）**: `/home/nario/ais-scripts/`
  - `ais_status.sh`
  - `ais_restart.sh`

### 9.2 各ツールの役割

| ファイル | 役割 | 内部処理 |
|---|---|---|
| `AIS_Open.bat` | 本番UI（Streamlit）をブラウザで開く | `start "" "https://campaignpilot.luvira.co.jp"` |
| `AIS_Status.bat` | 両serviceの状態と `/health` を確認する | SSH経由で `/home/nario/ais-scripts/ais_status.sh` を実行し、`systemctl status ad-insight-fastapi` / `ad-insight-streamlit` と `curl http://127.0.0.1:8000/health` の結果を表示 |
| `AIS_Restart.bat` | 両serviceを再起動し、直後の状態を確認する | SSH経由で `/home/nario/ais-scripts/ais_restart.sh` を実行し、`systemctl restart` 後に status と `/health` を表示 |

補足: 本番の正式アクセスURLは **`https://campaignpilot.luvira.co.jp`**（2026-07-03、Nginx + Let's Encrypt TLSで本番反映済み）。`AIS_Open.bat` も正式URLを開く設定に更新済み（2026-07-03）。`http://34.84.24.83:8501` 等の直アクセス経路は縮小方針が決まるまで引き続き到達可能。なお `34.84.24.83` はGCP静的外部IP（`ais-prod-static-ip` / `asia-northeast1`）として予約済みのため、VM再起動等でIPが変わることはありません。Nginx/TLSの適用済み設定・今後の直アクセス縮小検討は [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) の「Nginx / ドメイン移行チェックリスト」を参照してください。

### 9.3 利用手順（平常時）
1. `AIS_Open.bat` をダブルクリックする
2. ブラウザでStreamlit UIが開けば作業開始

### 9.4 障害時の使い分け
1. UIが開かない・分析が動かない等の異常に気づいたら、まず **`AIS_Status.bat`** をダブルクリックし、以下を確認する
   - `ad-insight-fastapi` / `ad-insight-streamlit` がともに `active (running)` か
   - `/health` が `{"status":"healthy",...}` を返しているか
2. いずれかが異常（`failed` / `activating (auto-restart)` 等）であれば **`AIS_Restart.bat`** をダブルクリックする
   - 両serviceを再起動し、そのまま status と `/health` を表示して結果を確認できる
3. 再起動後も改善しない場合は、本ドキュメント「8. 障害診断の最速フロー」に従い詳細調査を行う（ログ確認、`.env`/systemd設定確認等）。1クリックツールは一次切り分け・簡易復旧用であり、依存関係やコードレベルの問題解決は対象外。

### 9.5 注意事項
- どちらの bat も実行結果はウィンドウ内にそのまま表示され、最後にキー入力待ちになるため、閉じる前に内容を確認できる
- secrets（APIキー等）は bat・VM側スクリプトいずれにも含まれていない
- `AIS_Restart.bat` は対象2 service（`ad-insight-fastapi`, `ad-insight-streamlit`）以外には影響しない

### 9.6 sudo権限の最小化ポリシー（Phase 2-1）

AIS 1クリック運用（`ais_status.sh` / `ais_restart.sh`）が実際に必要とするsudo操作は、`ad-insight-fastapi` / `ad-insight-streamlit` の `status` / `restart` のみ。この最小権限を明示的に定義したポリシーを `infra/sudoers/ais-ops.template` としてリポジトリ管理している。

**適用手順:**
```bash
sudo cp infra/sudoers/ais-ops.template /etc/sudoers.d/ais-ops
sudo sed -i "s/{{APP_USER}}/<実際のOSユーザー名>/" /etc/sudoers.d/ais-ops
sudo chown root:root /etc/sudoers.d/ais-ops
sudo chmod 0440 /etc/sudoers.d/ais-ops
sudo visudo -c   # 構文検証（必須）
```

**注意事項:**
- 本番VMには GCP IAM/OS Login 由来の `%google-sudoers ALL=(ALL:ALL) NOPASSWD:ALL`（`/etc/sudoers.d/google_sudoers`）が別途存在する。これは本プロジェクトの管理外（IAMロールに基づきGoogle側で自動的に付与・同期される）であり、削除・変更は行っていない
- 上記の`infra/sudoers/ais-ops.template`は、AIS運用スクリプトが実際に必要とする権限を独立して定義したものであり、将来的に広範なIAM権限が絞られた場合でもAIS運用が継続できるようにするための最小権限ポリシー
- 新しいsudoersファイルを設置する際は、必ず`sudo visudo -c`で構文検証してから有効化すること（構文エラーのある`/etc/sudoers.d/`配下ファイルはsudo自体を機能不全にするリスクがある）
