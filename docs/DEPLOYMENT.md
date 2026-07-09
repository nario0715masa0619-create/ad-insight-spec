# Phase 3 本番デプロイ前チェックリスト

## 必須項目（デプロイ前に全確認）

### セキュリティ
- [ ] CORS_ORIGINS が本番ドメインに限定されている
- [ ] API_KEY（OPENAI_API_KEY, GEMINI_API_KEY）が環境変数で管理されている（.env はバージョン管理対象外）
- [ ] DEBUG=False に設定されている
- [ ] Secret ファイル（.env）が本番サーバーのバージョン管理対象外であることを確認

### エラーハンドリング・ロギング
- [ ] 構造化ログ（JSON形式）が有効化されている
- [ ] すべての API エンドポイントに例外ハンドラが統合されている
- [ ] request_id / trace_id がリクエスト・レスポンスヘッダに含まれている
- [ ] エラーレスポンスが統一フォーマット（success: false, error_code, request_id）に従っている

### データベース
- [ ] PostgreSQL が本番環境に配置・起動している
- [ ] DATABASE_URL が正しく設定されている
- [ ] DB バックアップが日次実行予定である
- [ ] テーブル初期化が完了している（AdInsight テーブル）

### アプリケーション設定
- [ ] API_TIMEOUT_SECONDS が適切に設定されている（推奨: 60秒）
- [ ] API_RATE_LIMIT が設定されている（推奨: 100 requests/minute）
- [ ] LOG_LEVEL が INFO 以上に設定されている

### デプロイ・起動
- [ ] サーバー起動スクリプト（systemd service または Docker）が用意されている
- [ ] ヘルスチェック（GET /health）が正常に応答することを確認
- [ ] リバースプロキシ（Nginx）で HTTPS が強制されている
- [ ] ログ出力先（stdout または ログファイル）が確認されている

### 監視・アラート
- [ ] エラーログを集約するログサービス（CloudWatch / ELK / Datadog）が設定されている
- [ ] API レスポンスタイム、エラー率のメトリクス収集が開始されている
- [ ] 重大エラー時のアラート通知が設定されている

## 次段階項目（本番稼働後の改善）

### 認証・認可
- [ ] JWT / OAuth による API 認証の実装
- [ ] ユーザー・テナント管理機構の構築

### 高度なセキュリティ
- [ ] WAF（Web Application Firewall）の導入
- [ ] DDoS 対策（CDN / 攻撃検知）
- [ ] 定期的なセキュリティ監査・脆弱性スキャン

### パフォーマンス最適化
- [ ] キャッシング層（Redis）の導入
- [ ] CDN（CloudFront / CloudFlare）の導入
- [ ] DB インデックス・クエリ最適化

### 非同期処理
- [ ] Celery による長時間分析のバックグラウンド化
- [ ] WebSocket による結果のリアルタイム通知

### 監視・可視化
- [ ] Grafana ダッシュボード構築
- [ ] SLA / SLI 定義・監視

### Secrets 管理の拡張
- [ ] AWS Secrets Manager / HashiCorp Vault への移行
- [ ] API キーの自動ローテーション

---

## デプロイ完了判定

上記「必須項目」の 12 項目すべてが確認されたら、本番デプロイ可能と判定します。

次段階項目は本番稼働開始後、段階的に実装してください。

---

## 具体的なデプロイ手順

### 1. 初期化手順
```bash
# 依存ライブラリインストール
pip install -r requirements.txt

# DB テーブル初期化（SQLite または PostgreSQL）
# 新規テーブルは初回起動時（app/main.py の Base.metadata.create_all）に自動生成されます。
# ただし create_all は「存在しないテーブルの新規作成」のみを行い、既存テーブルへの
# カラム追加・変更は行いません。既存テーブルのスキーマ変更は Alembic で行ってください
# （下記「1a. DBマイグレーション」参照）。

# 外部依存ツールのインストール確認
tesseract --version
ffmpeg -version
```

### 1a. DBマイグレーション（Alembic、2026-07-09〜）

`backend/alembic/` にマイグレーション一式があります（`backend/alembic.ini` の
`sqlalchemy.url` は意図的に空欄にしてあり、`app/db/session.py` と同じDB URLを
`alembic/env.py` が実行時に読み込みます。実行ディレクトリによって別々のDBを見て
しまう事故を避けるための設計です）。

**このリポジトリのDBに初めてAlembicを導入する場合**（本番DBは`create_all`のみで
作られており、Alembicのマイグレーション実行履歴を一切持っていません）:

```bash
cd backend
# 既存テーブルを再作成せず、「baselineマイグレーションまでは適用済み」と
# 印だけを付ける（実際のDDLは実行されない）
alembic stamp 5ce6bc069419

# 以降のマイグレーション（asset_data/evaluation_dataカラム追加など）を適用
alembic upgrade head
```

**新規環境（まっさらなDB）の場合**は、`stamp`せずに最初から通常どおり実行します:
```bash
cd backend
alembic upgrade head
```

**本番DBへの適用前には必ずバックアップを取得してください**
（`docs/POSTGRES_MIGRATION.md`のバックアップ手順と同様）:
```bash
cp ad_insight.db ad_insight.db.backup.$(date +%Y%m%d_%H%M%S)
```

以降、`AdInsight`モデルのスキーマを変更する際は、モデル変更と同時に
`alembic revision -m "..."`でマイグレーションファイルを作成し、`upgrade()`/
`downgrade()`を記述してください（`Base.metadata.create_all`頼みの変更はしない）。

### 2. Nginx ファイルサイズ上限設定案
アップロードされる画像や動画ファイルサイズを許容するため、Nginx側で上限を設定します。
```nginx
server {
    ...
    client_max_body_size 50M;  # ファイルアップロード上限 50MB
    ...
}
```
※FastAPI側でも必要に応じてリクエストサイズやファイルサイズのバリデーションを行います。

### 3. バックエンド起動コマンド（本番用）
```bash
export DEBUG=False
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="..."
export DATABASE_URL="postgresql://user:pass@localhost/ad_insight"
export CORS_ORIGINS="https://yourdomain.com"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. フロントエンド起動コマンド（手動・テスト用）
```bash
streamlit run frontend/streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

### 5. 環境変数 Smoke Test の実行（本番前確認）
バックエンド・フロントエンドを起動する前に、必須の環境変数が正しく認識されているかをテストします。機密情報は自動的にマスクされます。
```bash
# プロジェクトルートから実行
export PYTHONPATH=backend
python scripts/smoke_test_env.py
```
※ `PASSED` と表示されることを確認してから次の起動ステップへ進んでください。

### 6. システムデーモン (systemd) を用いた自動起動設定（本番推奨）
手動でのバックグラウンド起動 (`nohup` 等) は環境変数の欠落やプロセス監視の観点から非推奨です。
リポジトリ内の `infra/systemd/` にあるテンプレートを使用して自動起動を設定してください。

このテンプレートは、本番VMで実際に稼働・検証済みの構成（`WorkingDirectory` をリポジトリルートにし、`PYTHONPATH` で `backend` を解決する方式）と一致させてあります。**リポジトリの `infra/systemd/*.template` を正（canonical source）とし、VM上の実体ユニットファイルとの乖離が生じないようにしてください。** テンプレートを更新した場合は、本番VM側の `/etc/systemd/system/*.service` にも反映し、`daemon-reload` と対象サービスの再起動・状態確認まで行うこと。

**設定手順:**
1. テンプレートを systemd のディレクトリにコピーします（サービス名は `ad-insight-fastapi` / `ad-insight-streamlit` で統一）。
   ```bash
   sudo cp infra/systemd/fastapi.service.template /etc/systemd/system/ad-insight-fastapi.service
   sudo cp infra/systemd/streamlit.service.template /etc/systemd/system/ad-insight-streamlit.service
   ```
2. コピーしたファイルを開き、`{{APP_USER}}`, `{{APP_DIR}}`, `{{ENV_FILE_PATH}}` を実際の環境（例: `nario`, `/opt/ad-insight-spec`, `/etc/ad-insight-spec/.env` など）に合わせて書き換えます。
3. `EnvironmentFile` で指定したパス（例: `/etc/ad-insight-spec/.env`）に `.env` ファイルを配置し、アクセス権限を適切に設定します。
4. systemd に設定を反映させ、自動起動を有効化します。
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable ad-insight-fastapi ad-insight-streamlit
   sudo systemctl start ad-insight-fastapi ad-insight-streamlit
   sudo systemctl status ad-insight-fastapi ad-insight-streamlit --no-pager
   ```

### 7. ヘルスチェック確認
起動後、別ターミナルから以下のコマンドでバックエンドが正常に稼働しているか確認します。
```bash
curl http://localhost:8000/health
```

## GCP ファイアウォール設定に関する注意

### 問題：外部からポートにアクセスできない

**原因：**
- VPC ネットワークファイアウォール ポリシーを使用すると、複雑で設定が難しい
- 古いファイアウォール ルール方式の方がシンプルで確実

**解決方法：**
VPC ネットワークファイアウォール ポリシーは使用せず、「ファイアウォール ルール」を使用すること。

### 正しいファイアウォール ルール設定手順

GCP コンソール > VPC ネットワーク > ファイアウォール > ファイアウォール ルールを作成

以下の設定で各ポート用ルールを作成：

**Streamlit (8501) の場合：**
- 名前: allow-streamlit-8501
- ネットワーク: default
- 優先度: 1000
- トラフィック方向: Ingress
- アクション: 許可
- ターゲットタグ: http-server
- 送信元 IPv4 範囲: 0.0.0.0/0
- プロトコルとポート: tcp:8501

**FastAPI (8000) の場合も同様：**
- 名前: allow-fastapi-8000
- プロトコルとポート: tcp:8000

### firewall 棚卸しメモ（2026-07-03）

Secrets/公開経路の棚卸しの一環として、`default-allow-rdp`（tcp:3389, 0.0.0.0/0）を削除した。

- **削除理由**: 本番VMはDebian Linuxで、3389番ポートの待受プロセスは存在しなかった（RDPは未使用）。GCPプロジェクト作成時のデフォルトルールが消し忘れられていたもので、実際のサービスに紐づかない不要な公開経路だった
- **削除前確認**: `sudo ss -tlnp` で3389番の待受なしを確認
- **削除後確認**: `https://campaignpilot.luvira.co.jp/health`（200）、`http://34.84.24.83:8501`（200）、SSH到達性、`ad-insight-fastapi` / `ad-insight-streamlit` / `nginx` の稼働（active）、FastAPI `/health`（healthy）をすべて確認し、影響がないことを確認済み
- **現在のfirewallルール**: `default-allow-http`(80) / `default-allow-https`(443) / `allow-streamlit-8501`(8501) / `default-allow-ssh`(22) / `default-allow-icmp` / `default-allow-internal`（VPC内部のみ）
- **今後の検討事項（未実施）**: `allow-streamlit-8501` はHTTPS本番経路（Nginx）と並行して残っている直アクセス用ルール。閉鎖判断はHTTPS運用の安定確認後に別途行う（[docs/OPERATIONS.md](OPERATIONS.md) 参照）

## Nginx / ドメイン移行チェックリスト（Phase 2-3）

### 現状（2026-07-03 時点、本番反映済み）
- **`https://campaignpilot.luvira.co.jp` が本番公開URL。DNS / Nginx / TLS 切替が完了した**
- GCPの静的外部IPアドレス: `ais-prod-static-ip`（region: `asia-northeast1`）= `34.84.24.83`
- DNS: Xserver管理の `luvira.co.jp` ゾーンで `campaignpilot` のAレコードが `34.84.24.83` に設定済み・反映確認済み
- Nginx: 本番VMに導入済み（`apt-get install nginx`）、`/etc/nginx/sites-available/ais`（`infra/nginx/ais.conf.template` の `{{DOMAIN_NAME}}` を `campaignpilot.luvira.co.jp` に置換して生成）を `sites-enabled` に配置。デフォルトサイト（`sites-enabled/default`）は無効化済み
- TLS: `certbot --nginx -d campaignpilot.luvira.co.jp` で取得済み（Let's Encrypt、2026-10-01 失効予定、`certbot.timer` により自動更新）。HTTP→HTTPSリダイレクト（301）も certbot により自動設定済み
- 直アクセス経路（`http://34.84.24.83:8501` 等）は撤去しておらず、引き続き到達可能（縮小は本チェックリストの対象外・別タスク）

### 完了した前提条件
- [x] GCPで静的外部IPを予約する（`ais-prod-static-ip` / `34.84.24.83` / `asia-northeast1`）
- [x] 採用ドメイン決定（`campaignpilot.luvira.co.jp`）
- [x] Xserverの `luvira.co.jp` DNS管理画面で `campaignpilot` のAレコードを `34.84.24.83` に設定（DNS管理者側で実施済み）
- [x] DNS反映確認（`nslookup campaignpilot.luvira.co.jp 8.8.8.8` → `34.84.24.83`）
- [x] Nginx導入・設定適用・構文検証・reload
- [x] HTTP(80)疎通確認、TLS証明書取得、HTTPS(443)疎通確認
- [x] `/health`・Streamlit UI・WebSocket（`Upgrade`/`Connection`ヘッダ経由の101応答）の疎通確認

### 適用済み手順（記録）
0. `nslookup campaignpilot.luvira.co.jp 8.8.8.8` で `34.84.24.83` を確認
1. `sudo apt-get install -y nginx certbot python3-certbot-nginx`
2. `infra/nginx/ais.conf.template` の `{{DOMAIN_NAME}}` を `campaignpilot.luvira.co.jp` に置換し `/etc/nginx/sites-available/ais` に配置、`sites-enabled/ais` へのシンボリックリンクを作成、デフォルトサイトを無効化
3. `sudo nginx -t` → 構文OK
4. `sudo systemctl reload nginx`
5. `http://campaignpilot.luvira.co.jp/`・`/health` の200応答、既存IP直アクセスの継続稼働を確認
6. `sudo certbot --nginx -d campaignpilot.luvira.co.jp --agree-tos -m <管理者メール> --redirect` でTLS取得・HTTP→HTTPSリダイレクトを自動設定
7. `https://campaignpilot.luvira.co.jp/`・`/health`・WebSocketアップグレード（101）・Streamlit UIのHTML配信を確認

### 今後の検討事項（本チェックリストでは未実施・別タスク）
- `https://campaignpilot.luvira.co.jp` での運用が十分安定してから、IP直アクセス用ファイアウォールルール（`allow-streamlit-8501`, `allow-fastapi-8000`）の許可範囲縮小を検討する

### 注意
- FastAPI/Streamlitのsystemd構成（`ad-insight-fastapi`, `ad-insight-streamlit`）は変更不要。Nginxはあくまで手前に追加するリバースプロキシであり、両サービスは引き続き `127.0.0.1:8000` / `127.0.0.1:8501` で待受する
- StreamlitはWebSocket通信を使うため、Nginx設定に `Upgrade`/`Connection` ヘッダの転送が必須（`infra/nginx/ais.conf.template` に反映済み）
