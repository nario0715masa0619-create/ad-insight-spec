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

## 1-1. 初期プランを投入する（環境構築時に1度）

新しい環境（開発機・検証環境など）を用意したら、会社を作る前に初期プラン5種
（Monitor Beta / Starter / Growth / Pro / Enterprise）を投入してください。定義は
`scripts/seed_data/pricing_plans.json` にマスタデータとして保持しており、
価格・クレジット量・文言はこのJSONを編集するだけで調整できます（コード変更・
再デプロイ不要）。

```bash
cd backend
python ../scripts/manage_monitor_accounts.py seed-plans --dry-run   # まず反映内容を確認
python ../scripts/manage_monitor_accounts.py seed-plans             # 実際に投入/更新
python ../scripts/manage_monitor_accounts.py list-plans             # 結果を確認
```

- **何度実行しても安全**です（`code` をキーに upsert する。既存プランは値を最新化するだけで、
  重複作成はされません）。
- **`is_active` はseedの対象外**です。一度 `update-plan --code X --inactive` で無効化した
  プランは、seedを再実行しても復活しません（廃止判断は明示的な操作でのみ行う設計）。
- 価格やクレジット量を変えたい場合は `scripts/seed_data/pricing_plans.json` を編集して
  再実行するのが基本の運用です。個別のプランだけ即座に触りたい場合は
  「2-1. 価格・プランを定義する」の `update-plan` を使っても構いません（どちらも最終的に
  同じ `pricing_plans` テーブルを更新します）。
- **本番DBへの投入は今回のタスクでは行っていません。** 開発/検証環境での再現手段として
  整備したものです。本番反映時は「10. 本番反映時の注意」を参照してください。

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

## 2-1. 価格・プランを定義する（Starter/Growth/Pro/Monitor Beta/Enterpriseなど）

プラン名・価格・付与クレジット・マーケティング文言はコードではなく `pricing_plans`
テーブルで管理します。会社は個別上書きを持たない限り、紐づいたプランの
`monthly_credit_limit` を継承します（優先順位: 個別上書き > プラン > 既定値100。
詳細は [MONITOR_BETA_OPERATION.md](./MONITOR_BETA_OPERATION.md) 参照）。

**通常は「1-1. 初期プランを投入する」の `seed-plans` で5種とも揃うため、
このセクションは個別に1プランだけ追加・調整したい場合や、初期5種以外の
特別なプランを作りたい場合にのみ使ってください。**

### CLI
```bash
python scripts/manage_monitor_accounts.py create-plan --code growth --name "Growth" --price 99800 --credits 300
python scripts/manage_monitor_accounts.py create-plan --code monitor --name "Monitor Beta" --price 0 --credits 300 --private
python scripts/manage_monitor_accounts.py create-plan --code pro --name "Pro" --price 179800 --credits 650 \
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
  -d '{"code": "pro", "name": "Pro", "monthly_price_jpy": 179800, "monthly_credit_limit": 650, "marketing_note": "初期導入企業向けキャンペーン企画中", "display_order": 3}'

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

## 2-2. plan と override の使い分けルール

**基本方針: 会社には必ずプランを割り当て、個別上書き(override)は例外対応にのみ使う。**
「毎回overrideで微調整する」状態は運用が属人化するため避けてください。

| ケース | 推奨する扱い |
|---|---|
| 通常のモニター企業 | `monitor` プランを割り当てる（override無し） |
| 商用契約のStarter/Growth/Pro顧客 | 該当プランを割り当てる（override無し） |
| 今月だけ検証のため増枠したい | override を一時設定し、**検証が終わったら`clear-limit-override`で必ず戻す** |
| そのモニター企業だけ恒常的に上限が違う特殊契約 | override を設定したままにする（この場合はoverrideが「その会社の契約内容」を表すので妥当） |
| Enterprise（個別契約） | `enterprise` プランを割り当てたうえで、契約ごとの実際の上限を override で設定するのが基本
  （`enterprise`プラン自体のクレジット量はあくまで仮の値であり、個々の契約はほぼ必ずoverrideを伴う） |
| プランを何も割り当てていない会社 | 既定値（100クレジット）にフォールバックするが、**これは暫定状態**として扱い、
  早めに `monitor` または該当プランを割り当てること（`list-usage`の`limit source`列が
  `fallback`の会社は、割り当て漏れの可能性を疑う） |

**`is_public=false` のプラン（Monitor Beta/Enterprise）について**: これは「外部の価格表ページに
表示するかどうか」を区別するためだけのフラグで、機能的な制限は一切ありません
（`is_public=false`でも通常どおり会社に割り当てて使えます）。今回は価格表ページ自体を
実装していないため、実運用上は「Monitor Beta/Enterpriseは一般顧客向けに営業提案する対象では
ない」という位置づけの記録以上の意味は持ちません。

**`monthly_credit_limit=0` について**: 0は無効な値やバグではなく、「アカウントは
`is_active=true`のまま、今月の分析実行だけを完全に止める」という正当な設定です
（例: 支払い遅延中の一時停止、契約更新待ちなど、アカウント自体を止めるほどではないが
新規分析はさせたくないケース）。会社作成(`create-company --limit 0`)・上限変更
(`set-limit --limit 0`)、管理API(`monthly_credit_limit: 0`)のいずれでも同じ意味で
使えます（以前はCLIでのみ0を許容しAdmin APIでは`422`になる不整合があったため、
両者を`0`以上許容で統一しました）。負の値は両経路とも拒否されます。

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
slug                 name                     limit source       active   used/limit(credits)   remaining
acme                 株式会社Acme              plan:growth        True     12/300                288
sample-monitor       サンプル社（モニター）     plan:monitor       True     8/300                 292
special-co           特別契約社                override           True     40/500                460
new-co               新規登録直後の会社          fallback           True     0/100                 100
```

`limit source` 列は実効上限がどこから来ているかを示します。
- `plan:<code>` — 割り当てたプランの値を使用中（通常の状態）
- `override` — 会社ごとの個別上書きを使用中
- `plan:<code>(inactive)` — プランは割り当てられているが無効化/期間外のため無視され、
  実際にはフォールバックへ落ちている（要確認）
- `fallback` — プランも上書きも無く既定値(100)を使用中（多くの場合、割り当て漏れ）

管理APIでは `GET /api/v1/admin/companies` が同等の情報（`limit_source` フィールド、および
`usage_this_month`、単位はクレジット）を返します。個々の消費履歴（誰が・いつ・どのモードで・
何クレジット消費したか）は`credit_usage_logs` テーブルに記録されますが、今回のスコープでは
一覧APIは用意していません（必要な場合はDBを直接参照するか、別途エンドポイント追加を検討してください）。

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

## 8. 新規モニター企業オンボーディングのクイックスタート

初めてモニター企業を迎える際の一連の流れです（環境構築直後で「1-1. 初期プランを投入する」
が済んでいる前提）。

```bash
cd backend

# 1. 会社を作成（この時点ではプラン未割当）
python ../scripts/manage_monitor_accounts.py create-company --name "株式会社Acme" --slug acme

# 2. 初期プラン一覧を確認
python ../scripts/manage_monitor_accounts.py list-plans

# 3. モニター企業向けプランを割り当てる（override無しで開始するのが基本）
python ../scripts/manage_monitor_accounts.py assign-plan --company-slug acme --plan-code monitor

# 4. ユーザーを招待する
python ../scripts/manage_monitor_accounts.py create-user --company-slug acme --email tanaka@acme.example

# 5. 割り当て内容と利用状況を確認する
python ../scripts/manage_monitor_accounts.py list-usage

# 6. （必要な場合のみ）個別上書きを設定し、不要になったら解除する
python ../scripts/manage_monitor_accounts.py set-limit --company-slug acme --limit 150
python ../scripts/manage_monitor_accounts.py clear-limit-override --company-slug acme
```

ステップ1で `--limit` を指定していない点に注意してください。プラン割り当て前提の
運用では、会社作成時に個別の数値を決め打ちしないほうが、後から
「なぜこの数字なのか」を追いかけずに済みます。

## 8-1. ログイン案内テンプレート（先方へ送る文面）

ステップ4でユーザーを作成すると、標準出力に一度だけ初期パスワードが表示されます
（`--password`省略時。DBには平文で保存されないため、この出力を取り逃すと
`reset-password`での再発行以外に確認手段はありません）。これを社内パスワード管理
ツール等に控えたうえで、先方には以下のような文面で個別に案内してください
（メール送信機能自体はサービスに無いため、Slack・メール等の別チャネルで手動送付）。

```
件名: CampaignPilot モニターベータ ログイン情報のご案内

株式会社Acme ご担当者様

このたびはCampaignPilotモニターベータにご協力いただきありがとうございます。
下記の情報でログインいただけます。

URL: https://campaignpilot.luvira.co.jp
メールアドレス: tanaka@acme.example
初期パスワード: （別チャネルでお伝えします）

- 本サービスはベータ版のため、画面・機能は予告なく変更される場合があります。
- パスワードの自己変更機能は現在ありません。変更したい場合はご連絡ください。
- 今月のご利用上限は100クレジットです（詳細は初回ログイン後、画面左サイドバーでご確認いただけます）。
- ご不明点・不具合はこのメールへの返信でお知らせください。
```

**初期パスワードは、この案内文面とは別チャネル・別メッセージで送付してください**
（同じメールに書くと、メール経路が漏えいした場合にID・パスワードの両方が
同時に流出するため）。

## 8-2. 利用開始前チェックリスト（先方に案内を送る前に確認）

先方へログイン案内を送る前に、次を確認してください。

- [ ] `list-usage` で当該会社の `limit source` が `plan:monitor`（または合意した
  プラン）になっている（`fallback`のまま案内すると、意図せず既定値100クレジットの
  会社として運用が始まってしまう）
- [ ] `list-plans` で割り当てたプランが `active=True` である
  （無効化済みプランを割り当てていないか）
- [ ] 個別上書き(override)を使う契約の場合、`set-limit`が正しい値で反映されている
  （`list-usage`の`limit source`が`override`、`used/limit`の`limit`側が合意値と一致）
- [ ] 作成したユーザーの`is_active`が有効（作成直後はデフォルトで有効だが、誤って
  他社のユーザーを操作していないか`list-usage`や管理APIで確認）
- [ ] 実際に発行したメールアドレス・パスワードで自分自身が一度ログインでき、
  サイドバーに正しい会社名・プラン・利用状況（`0/上限値`）が表示されることを確認済み
  （CLI上の作成成功メッセージだけでなく、ログイン導線そのものを一度通しておく）
- [ ] 上記が確認できてから、「8-1. ログイン案内テンプレート」で先方に案内する

## 9. よくある運用パターン

**新規モニター企業の受け入れ**: 上記クイックスタートのとおり、`monitor` プランを
割り当てるだけで完了します。個別の交渉が必要な特別条件がある場合のみ override を使います。

**一時的な増枠（検証・キャンペーン等）**:
```bash
python scripts/manage_monitor_accounts.py set-limit --company-slug acme --limit 300
# ...検証期間が終わったら必ず戻す...
python scripts/manage_monitor_accounts.py clear-limit-override --company-slug acme
```
override を設定しっぱなしにしないよう、`notes`（`PATCH /api/v1/admin/companies/{id}`の
`notes`フィールド、CLIには未対応）に「いつまでの一時増枠か」を書き残しておくことを推奨します。

**モニター企業が商用プランへ移行する（例: Monitor Beta → Growth）**:
```bash
python scripts/manage_monitor_accounts.py assign-plan --company-slug acme --plan-code growth --clear-override
```
`--clear-override` を付けることで、Monitor時代に個別上書きが残っていても確実にGrowthの
上限へ切り替わります。

**Enterprise（個別契約）の会社を追加する**:
```bash
python scripts/manage_monitor_accounts.py assign-plan --company-slug bigcorp --plan-code enterprise
python scripts/manage_monitor_accounts.py set-limit --company-slug bigcorp --limit 5000   # 契約内容に応じた実際の上限
```
`enterprise` プランのクレジット量はあくまで仮の値なので、実運用では必ず override で
契約内容に応じた実際の値を設定してください。

**価格・プラン内容を見直す（全社に反映したい場合）**:
`scripts/seed_data/pricing_plans.json` を編集し、`seed-plans --dry-run` で変更内容を
確認してから `seed-plans` を実行してください。そのプランを使っている全社の実効上限に
即座に反映されます（個別上書きを持つ会社は影響を受けません）。

**プランを廃止する**:
```bash
python scripts/manage_monitor_accounts.py update-plan --code legacy-plan --inactive
```
割り当てられていた会社は次回アクセス時から自動的にフォールバック値（100クレジット）に
落ちます。`list-usage`で`limit source`が`plan:legacy-plan(inactive)`と表示されるので、
該当会社には別のプランを速やかに割り当て直してください。

## 10. 本番反映時の注意（CLAUDE.md準拠）

**マージ後に実際に本番適用する際の順序立てた手順・ロールバック観点・事前チェック項目は
[docs/plans/monitor_beta_post_merge_runbook.md](./plans/monitor_beta_post_merge_runbook.md)
に集約しています。** 以下はその要点の抜粋です。

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
- `scripts/seed_data/pricing_plans.json` の投入（`seed-plans`）は**本番DBに対しては
  実行していません**。本番へ反映する場合も、まずマイグレーション適用後に
  `seed-plans --dry-run` で内容を確認してから実行することを推奨します
  （冪等なので誤って複数回実行しても壊れませんが、実DBに向けた初回実行は
  他の変更と同様に計画的に行ってください）。
