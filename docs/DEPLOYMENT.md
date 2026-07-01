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

### 4. フロントエンド起動コマンド（本番用）
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

### 6. ヘルスチェック確認
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
