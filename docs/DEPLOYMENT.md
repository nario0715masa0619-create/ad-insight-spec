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
# SQLiteの場合: 初回起動時に自動生成されます。
# PostgreSQLの場合: 事前にDBを作成し、AlembicやSQLスクリプトでテーブルを作成してください。

# 外部依存ツールのインストール確認
tesseract --version
ffmpeg -version
```

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

## Nginx / ドメイン移行チェックリスト（Phase 2-3）

### 現状（2026-07-03 時点で確認済み、採用ドメイン決定後）
- 採用ドメインは **`campaignpilot.luvira.co.jp`** に決定
- 公開経路は現状 IP 直アクセスのみ（`http://34.84.24.83:8501`、FastAPI は `:8000`）
- Nginx は本番VMに未インストール。80/443番ポートはファイアウォール上は開いているが、待受プロセスがない
- GCPの静的外部IPアドレスは予約済み: `ais-prod-static-ip`（region: `asia-northeast1`）= `34.84.24.83`
- TLS証明書は未取得

**ブロッカー（2026-07-03 調査で判明、未解消）:**
- `luvira.co.jp` の権威DNSは GCP Cloud DNS ではなく **Xserver**（`ns1〜ns5.xserver.jp`）が管理している。この実行環境（gcloud CLI / GitHub操作用の認証情報）では Xserver 側のDNS管理画面・APIへのアクセス手段が無く、Aレコードを変更できない
- `campaignpilot.luvira.co.jp` は現時点で既に `85.131.213.56`（Xserverの共有ホスティングIPと推測。AISのVM・静的IPとは無関係）を指しており、HTTP/HTTPS双方で応答が返る状態（Xserver側の「無効なURLです」という汎用エラーページ。AIS用に設定されたものではなく、`luvira.co.jp` 配下の未設定サブドメイン向けデフォルト応答と見られる）
- 上記のため、DNS Aレコードの向け先変更には **Xserverのサーバーパネル／ドメインパネルでの操作、またはXserver側DNS管理者によるAレコード追加**が必要（本環境からは実行不可）

上記の理由により、**本番のNginx/ドメイン切替は未実施**。`infra/nginx/ais.conf.template` として設定テンプレートのみ用意し、DNS切替が完了次第すぐに適用できる状態にした。

### 切替に必要な前提条件（すべて揃うまで本番切替しないこと）
- [x] GCPで静的外部IPを予約する（完了: `ais-prod-static-ip` / `34.84.24.83` / `asia-northeast1`）
- [x] 採用ドメイン決定（完了: `campaignpilot.luvira.co.jp`）
- [ ] **Xserverの `luvira.co.jp` DNS管理画面（またはドメインのネームサーバーパネル）から `campaignpilot` のAレコードを `34.84.24.83` に向ける（未実施・要Xserver管理者作業）**
- [ ] DNS反映確認（`nslookup campaignpilot.luvira.co.jp` が `34.84.24.83` を返すこと。Xserverの旧レコードのTTL＝3600秒のため反映まで最大1時間程度を見込む）

### 切替手順（DNS切替後、すぐ再開できる状態）
0. Xserverの `luvira.co.jp` DNS設定で `campaignpilot` のAレコードを `34.84.24.83` に向け、`nslookup campaignpilot.luvira.co.jp 8.8.8.8` で `34.84.24.83` を返すことを確認する
1. Nginxをインストール: `sudo apt-get update && sudo apt-get install -y nginx`
2. `infra/nginx/ais.conf.template` の `{{DOMAIN_NAME}}` を `campaignpilot.luvira.co.jp` に置換し、`/etc/nginx/sites-available/ais` に配置
3. `sudo ln -s /etc/nginx/sites-available/ais /etc/nginx/sites-enabled/ais`
4. `sudo nginx -t` で構文検証（エラーがあれば有効化しない）
5. `sudo systemctl reload nginx`（Nginx未起動なら `enable --now nginx`）
6. ドメイン経由でHTTP到達確認（UI表示・`/health`・分析実行）を、**既存のIP直アクセスを止めずに**並行して行う
7. TLS化: `sudo certbot --nginx -d campaignpilot.luvira.co.jp`（Let's Encrypt、証明書自動更新はcertbotのsystemd timerに従う）
8. `https://campaignpilot.luvira.co.jp` での動作（`/health`、Streamlit UI、WebSocket通信）を十分に確認できてから、IP直アクセス用ファイアウォールルール（`allow-streamlit-8501`, `allow-fastapi-8000`）の許可範囲を縮小することを検討する（本チェックリストでは実施しない。別タスクとする）

### 注意
- FastAPI/Streamlitのsystemd構成（`ad-insight-fastapi`, `ad-insight-streamlit`）は変更不要。Nginxはあくまで手前に追加するリバースプロキシであり、両サービスは引き続き `127.0.0.1:8000` / `127.0.0.1:8501` で待受する
- StreamlitはWebSocket通信を使うため、Nginx設定に `Upgrade`/`Connection` ヘッダの転送が必須（`infra/nginx/ais.conf.template` に反映済み）
