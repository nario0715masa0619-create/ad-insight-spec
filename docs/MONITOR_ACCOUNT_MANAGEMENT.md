# モニターアカウント管理ガイド（管理者向け）

招待制モニターベータの会社・ユーザー・月間利用上限を管理する手順です。
専用の管理画面は今回のスコープでは用意しておらず、次の2つの経路のいずれかで運用します。

- **CLI**: `scripts/manage_monitor_accounts.py`（最初の管理者アカウント発行など、まだ誰も
  ログインできない状態からのブートストラップに必須）
- **管理API**: `/api/v1/admin/*`（`is_admin=true` のログイン済みユーザーのみ利用可能）

モニター利用者側の視点（ログイン方法・月間上限の考え方・上限到達時の挙動）は
[MONITOR_BETA_OPERATION.md](./MONITOR_BETA_OPERATION.md) を参照してください。

## 1. 事前準備: 最初の管理者アカウントを作る

管理API自体がログイン必須のため、誰もログインできない最初の状態では管理APIを叩けません。
最初の会社・管理者ユーザーは必ずCLIで作成してください。

```bash
cd backend
python ../scripts/manage_monitor_accounts.py create-company --name "自社（管理用）" --slug internal --limit 100000
python ../scripts/manage_monitor_accounts.py create-user --company-slug internal --email admin@example.com --admin
```

`--password` を指定しない場合はランダムなパスワードが生成され、標準出力に一度だけ表示されます。
このパスワードは別チャネル（社内パスワード管理ツール等）で保管し、標準出力の履歴からは消してください。

以降のモニター企業・ユーザーは、この管理者アカウントでログインして管理APIから追加しても、
引き続きCLIで追加しても構いません。

## 2. モニター企業を追加する

### CLI
```bash
python scripts/manage_monitor_accounts.py create-company --name "株式会社Acme" --slug acme --limit 50
```

### 管理API
```bash
curl -X POST http://localhost:8000/api/v1/admin/companies \
  -H "Authorization: Bearer <管理者のsession_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "株式会社Acme", "slug": "acme", "monthly_analysis_limit": 50}'
```

- `slug` は英数字のユニークID（URLや他コマンドの引数として使う）。日本語不可・重複不可。
- `monthly_analysis_limit` は月間分析実行回数の上限（デフォルト50）。特に理由がなければ
  会社単位・月1日リセットのままにしてください（[MONITOR_BETA_OPERATION.md](./MONITOR_BETA_OPERATION.md) 参照）。

## 3. モニターユーザーを招待する

### CLI
```bash
python scripts/manage_monitor_accounts.py create-user --company-slug acme --email tanaka@acme.example
```
パスワードを指定しない場合はランダム生成され、標準出力に表示されます。これを別チャネルで
本人に伝えてください（このサービス自体にメール送信機能はありません）。

### 管理API
```bash
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer <管理者のsession_token>" \
  -H "Content-Type: application/json" \
  -d '{"company_id": 2, "email": "tanaka@acme.example"}'
```
レスポンスの `generated_password` は初回のみ返されます（DBには平文で保存されないため、
このレスポンスを取り逃すと再発行以外に確認方法はありません）。

管理者権限を付与する場合は `"is_admin": true` を指定してください。

## 4. 上限を変更する

```bash
python scripts/manage_monitor_accounts.py set-limit --company-slug acme --limit 100
```
または `PATCH /api/v1/admin/companies/{company_id}` に `{"monthly_analysis_limit": 100}` を送信。

変更は即時反映されます（当月の残り利用回数の再計算も次回のリクエストから自動的に新しい上限で行われます）。

## 5. 利用状況を確認する

```bash
python scripts/manage_monitor_accounts.py list-usage
```
```
slug                 name                     active   used/limit   remaining
acme                 株式会社Acme              True     12/50        38
```

管理APIでは `GET /api/v1/admin/companies` が同等の情報（会社ごとの `usage_this_month`）を返します。

## 6. 会社・ユーザーを停止/再開する

会社ごと止める（その会社の全ユーザーが即座にログイン・操作不能になる）:
```bash
python scripts/manage_monitor_accounts.py deactivate-company --company-slug acme
python scripts/manage_monitor_accounts.py reactivate-company --company-slug acme
```

ユーザー単体を止める:
```bash
python scripts/manage_monitor_accounts.py deactivate-user --email tanaka@acme.example
python scripts/manage_monitor_accounts.py reactivate-user --email tanaka@acme.example
```

管理APIでは `PATCH /api/v1/admin/companies/{id}` の `{"is_active": false}` /
`PATCH /api/v1/admin/users/{id}` の `{"is_active": false}` が同等です。

停止は即時反映されます（ログイン済みセッションがあっても、次のリクエストから401になります）。

## 7. パスワードを再発行する

```bash
python scripts/manage_monitor_accounts.py reset-password --email tanaka@acme.example
```
`--password` を指定しない場合はランダム生成され、標準出力に表示されます。
管理APIでは `PATCH /api/v1/admin/users/{id}` に `{"new_password": "..."}` を送信します。

## 8. 本番反映時の注意（CLAUDE.md準拠）

- この機能一式はDBスキーマ変更（Alembicマイグレーション `f3a1c9d2e8b0`）を含みます。
  本番DBへの適用（`alembic upgrade head`）はCLAUDE.mdの方針に従い、依存関係確認・
  バックアップ確認のうえ、別タスクとして慎重に実施してください。このPR自体では
  本番マイグレーションは実行していません。
- 既存の `ad_insights` レコードは `company_id` が `NULL` のまま残ります（データは消えません。
  単にどのモニター企業のスコープにも入らなくなるだけです）。
- 環境変数・secrets の追加はありません（パスワードハッシュは標準ライブラリの
  PBKDF2のみで生成し、外部ライブラリや追加のsecret keyを必要としません）。
