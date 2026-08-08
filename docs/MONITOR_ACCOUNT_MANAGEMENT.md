# モニターアカウント管理ガイド（管理者向け）

招待制モニターベータの会社・ユーザー・月次クレジット上限を管理する手順です。
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
python ../scripts/manage_monitor_accounts.py create-company --name "自社（管理用）" --slug internal --limit 1000000
python ../scripts/manage_monitor_accounts.py create-user --company-slug internal --email admin@example.com --admin
```

`--password` を指定しない場合はランダムなパスワードが生成され、標準出力に一度だけ表示されます。
このパスワードは別チャネル（社内パスワード管理ツール等）で保管し、標準出力の履歴からは消してください。

以降のモニター企業・ユーザーは、この管理者アカウントでログインして管理APIから追加しても、
引き続きCLIで追加しても構いません。

## 2. モニター企業を追加する

### CLI
```bash
python scripts/manage_monitor_accounts.py create-company --name "株式会社Acme" --slug acme --limit 100
```

### 管理API
```bash
curl -X POST http://localhost:8000/api/v1/admin/companies \
  -H "Authorization: Bearer <管理者のsession_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "株式会社Acme", "slug": "acme", "monthly_credit_limit": 100}'
```

- `slug` は英数字のユニークID（URLや他コマンドの引数として使う）。日本語不可・重複不可。
- `--limit`/`monthly_credit_limit` は会社ごとの**個別上書き**です。省略した場合、
  その会社は個別上書きを持たない状態（NULL）で作成され、後述のプランに紐づけるか、
  何も紐づけなければ既定値（100クレジット）にフォールバックします。

## 2-1. 価格・プランを定義する（Starter/Growth/Pro/Monitor/Enterpriseなど）

プラン名・価格・付与クレジット・マーケティング文言はコードではなく `pricing_plans`
テーブルで管理します。会社は個別上書きを持たない限り、紐づいたプランの
`monthly_credit_limit` を継承します（優先順位: 個別上書き > プラン > 既定値100。
詳細は [MONITOR_BETA_OPERATION.md](./MONITOR_BETA_OPERATION.md) 参照）。

### CLI
```bash
python scripts/manage_monitor_accounts.py create-plan --code growth --name "Growth" --price 79800 --credits 300
python scripts/manage_monitor_accounts.py create-plan --code monitor --name "Monitor" --credits 100 --private
python scripts/manage_monitor_accounts.py create-plan --code pro --name "Pro" --price 149800 --credits 650 \
  --note "初期導入企業向けキャンペーン企画中"
python scripts/manage_monitor_accounts.py list-plans
python scripts/manage_monitor_accounts.py update-plan --code pro --credits 700
python scripts/manage_monitor_accounts.py update-plan --code pro --inactive   # 廃止したプランを止める
```

### 管理API
```bash
curl -X POST http://localhost:8000/api/v1/admin/plans \
  -H "Authorization: Bearer <管理者のsession_token>" \
  -H "Content-Type: application/json" \
  -d '{"code": "pro", "name": "Pro", "monthly_price_jpy": 149800, "monthly_credit_limit": 650, "marketing_note": "初期導入企業向けキャンペーン企画中", "display_order": 3}'

curl http://localhost:8000/api/v1/admin/plans \
  -H "Authorization: Bearer <管理者のsession_token>"

curl -X PATCH http://localhost:8000/api/v1/admin/plans/3 \
  -H "Authorization: Bearer <管理者のsession_token>" \
  -H "Content-Type: application/json" \
  -d '{"monthly_credit_limit": 700}'
```

- `code` は一意な英数字ID（例: `starter`, `growth`, `pro`, `monitor`, `enterprise`）。会社への
  紐付けはAPI/CLIどちらも `code` を渡せば内部でID解決します（DB上のFKは`plan_id`によるID参照）。
- `monthly_price_jpy` は個別見積プラン（Enterprise等）ではNULLのままで構いません
  （CLIは `--price` を省略）。
- `is_public`（CLIは `--private` フラグ）は「公開プラン一覧に出すか」の区分ですが、
  今回のスコープでは実際に公開する画面（価格表ページ）自体は未実装です。あくまで
  将来そのような画面を作る際の区分として保持しています。
- `effective_from`/`effective_to` は今回CLIからは設定できません（必要なら管理APIで
  直接指定してください）。両方NULLなら常時有効です。無効化したいだけなら
  `is_active=false`（CLIは `--inactive`）で十分です。

### 会社にプランを割り当てる
```bash
python scripts/manage_monitor_accounts.py assign-plan --company-slug acme --plan-code growth
# 個別上書きが残っていると優先されてしまうため、プランをすぐ反映させたい場合は --clear-override も付ける
python scripts/manage_monitor_accounts.py assign-plan --company-slug acme --plan-code growth --clear-override
```
管理APIでは `PATCH /api/v1/admin/companies/{company_id}` に `{"plan_id": 3}` を送信します。

### 個別上書きを解除してプラン任せに戻す
```bash
python scripts/manage_monitor_accounts.py clear-limit-override --company-slug acme
```
管理APIでは `PATCH /api/v1/admin/companies/{company_id}` に `{"clear_credit_limit_override": true}`
を送信します（`monthly_credit_limit`と同時に指定した場合はclearが優先されます）。

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

## 4. クレジット上限を変更する

会社ごとの個別上書きを直接変更したい場合（プラン変更ではなく、その会社だけ特別に
上限を変えたい場合）:
```bash
python scripts/manage_monitor_accounts.py set-limit --company-slug acme --limit 200
```
または `PATCH /api/v1/admin/companies/{company_id}` に `{"monthly_credit_limit": 200}` を送信。

変更は即時反映されます（当月の残りクレジットの再計算も次回のリクエストから自動的に新しい上限で行われます）。
プランに乗せている会社の上限をまとめて変えたい場合は、個社ごとに`set-limit`するのではなく
「2-1. 価格・プランを定義する」の `update-plan` でプラン側の`monthly_credit_limit`を
変更してください（そのプランに紐づく全社に自動で反映されます。個別上書きを持つ会社は除く）。

## 4-1. 分析タイプ別の消費クレジット数を変更する

分析1回あたりの消費クレジット数（Light/Standard/Heavy = 1/2/3）は、会社ごとではなく
**アプリ全体の設定**として、環境変数で調整します（管理画面はまだ用意していません）。

```env
CREDIT_COST_LIGHT=1      # クリエイティブ単体分析（file_only）
CREDIT_COST_STANDARD=2   # + LP分析（file_plus_lp）
CREDIT_COST_HEAVY=3      # + LP + KPI分析（file_plus_lp_plus_manual_kpi）
```

`.env`（`app/config.py`が読み込むパス。CLAUDE.md準拠でリポジトリ直下には置かない）に設定し、
バックエンドを再起動すると反映されます。コード変更・DBマイグレーションは不要です。

## 5. 利用状況を確認する

```bash
python scripts/manage_monitor_accounts.py list-usage
```
```
slug                 name                     active   used/limit(credits)   remaining
acme                 株式会社Acme              True     12/100                88
```

管理APIでは `GET /api/v1/admin/companies` が同等の情報（会社ごとの `usage_this_month`、
単位はクレジット）を返します。個々の消費履歴（誰が・いつ・どのモードで・何クレジット消費したか）は
`credit_usage_logs` テーブルに記録されますが、今回のスコープでは一覧APIは用意していません
（必要な場合はDBを直接参照するか、別途エンドポイント追加を検討してください）。

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

- この機能一式はDBスキーマ変更（Alembicマイグレーション `f3a1c9d2e8b0` および
  `pricing_plans` テーブル・`monitor_companies.plan_id` を追加する `b7e2f4a1c3d5`）を
  含みます。本番DBへの適用（`alembic upgrade head`）はCLAUDE.mdの方針に従い、
  依存関係確認・バックアップ確認のうえ、別タスクとして慎重に実施してください。
  このPR自体では本番マイグレーションは実行していません。
- 既存の `ad_insights` レコードは `company_id` が `NULL` のまま残ります（データは消えません。
  単にどのモニター企業のスコープにも入らなくなるだけです）。
- `monitor_companies.monthly_credit_limit` は本マイグレーションで NOT NULL から
  nullable に変わります（NULL=「個別上書きなし」の意味）。ダウングレード時は
  NULL行を既定値100で埋め戻してからNOT NULL制約を復元します。
- 環境変数・secrets の追加はありません（パスワードハッシュは標準ライブラリの
  PBKDF2のみで生成し、外部ライブラリや追加のsecret keyを必要としません）。
