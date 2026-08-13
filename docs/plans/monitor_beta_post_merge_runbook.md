# モニターベータ PR #91 マージ後 運用開始runbook

## このドキュメントの位置づけ

[PR #91](https://github.com/nario0715masa0619-create/ad-insight-spec/pull/91)
（招待制ログイン・クレジット制利用上限・プラン外出し一式）が `main` にマージされてから、
実際にモニター企業を受け入れるまでの**一度きりの立ち上げ手順**をまとめたものです。

- 日常のアカウント運用（会社追加・上限変更・停止等）は
  [MONITOR_ACCOUNT_MANAGEMENT.md](../MONITOR_ACCOUNT_MANAGEMENT.md) を参照してください。
  本ドキュメントはそれらのコマンドを**どの順番で・どの環境に対して初めて実行するか**に
  焦点を当てています。
- モニター企業向けの画面挙動・FAQは [MONITOR_BETA_OPERATION.md](../MONITOR_BETA_OPERATION.md)、
  設計判断の背景は [campaignpilot_credit_billing_design.md](../campaignpilot_credit_billing_design.md)
  を参照してください。
- 本番デプロイ全般のチェックリストは [DEPLOYMENT.md](../DEPLOYMENT.md) /
  [OPERATIONS.md](../OPERATIONS.md) にあり、本ドキュメントはそのうち
  「招待制モニターベータ機能に固有の部分」を掘り下げたものです。
- **本番がPostgresの場合の追加確認事項**は
  [monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md) を参照してください。
  以下の「リハーサル実施記録」はSQLiteで実施したものですが、同じ手順をPostgres環境でも
  別途リハーサルし、機能的な差分が無いことを確認済みです。
- **「本番適用そのものをいつ・どちらのDBに対して行うか」の方針整理**は
  [monitor_beta_production_prerequisites.md](./monitor_beta_production_prerequisites.md) を
  参照してください。本番のPostgres移行自体は[Issue #80](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/80)
  系列として別途進行中・未完了であり、モニターベータの本番適用はそれとは独立に
  本番SQLiteへ先行して行える可能性が高いという結論をまとめています。

**現状（2026-08-09時点）**: PR #91はまだ `main` にマージされていません（`state: OPEN`）。
このドキュメントはマージ後を前提とした準備であり、本ドキュメント自体の作成・
以下のリハーサルはすべて隔離した使い捨てSQLite DBに対して行い、本番・開発中の
実DBには一切接続していません（Postgres版の隔離リハーサルは別途
[monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md) で実施）。

## 全体の流れ

```
Phase 1: マージ直後（コードのみ。本番には無影響）
   ↓
Phase 2: 本番適用前チェック（判断・確認のみ。ここでは何も実行しない）
   ↓
Phase 3: 本番適用（実際にDBに変更を加える。慎重に・別タスクとして）
   ↓
Phase 4: モニター1社目オンボーディング（MONITOR_ACCOUNT_MANAGEMENT.md §8/8-1/8-2）
```

## Phase 1: マージ直後にやること

- [ ] `main` へのマージ自体は本番に一切影響しません（本番は現在のコードのまま稼働継続。
  デプロイは別の明示的な操作です）。CLAUDE.mdの方針どおり、マージとデプロイは分離して考えます。
- [ ] マージ後の `main` で `pytest backend/tests` を一度実行し、マージ操作自体が
  何かを壊していないことを確認する（PR単体では確認済みだが、他ブランチとの
  マージ順序によっては差分が生まれる可能性があるため）。
- [ ] Phase 3（本番適用）の実施タイミングを決める。即座に本番へ適用する必要はなく、
  「コードはmainにあるが本番はまだ旧コードのまま」という状態を意図的に維持してもよい。

## Phase 2: 本番適用前チェック（確認のみ・ここでは実行しない）

本番DBへの変更は本タスクのスコープ外のため、以下は**判断材料の整理**であり、
実際のコマンド実行はPhase 3を別途計画的に行うタイミングで実施してください。

**本番がPostgresの場合**は、以下に加えて
[monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md)
「本番適用前チェック項目（Postgres観点の追加分）」も確認してください
（エンコーディング、接続ユーザー権限、SSL要否等）。

### バックアップ方針

- [x] ~~本番DBの直近バックアップが存在し、リストア手順が分かっている~~ →
  読み取り専用調査で確認済み。**自動バックアップは存在せず、約31日前・古いスキーマの
  手動バックアップが1件のみ、DBと同一ディスクに保存**という状態でした。リストア手順も
  正式には文書化されていません。詳細・リスク整理: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md)。
  **本番適用の直前に、最低限もう一度手動バックアップを取得することを強く推奨します**
  （実行はしていません）。
- [x] ~~本番が現在SQLiteかPostgresかを確認する~~ → 読み取り専用SSHで確認済み。
  **本番は現在SQLite**（`/opt/ad-insight-spec/ad_insight.db`）。`docs/OPERATIONS.md`の
  Postgres想定記述は現状と一致していません。

### 既存データ確認

- [x] ~~本番の `ad_insights` に既存レコードがあるか確認する~~ → 確認済み。**69件**存在。
  マイグレーション後は`company_id IS NULL`のまま残り、モニター企業のどの一覧にも
  表示されなくなります（データは消えないが、スコープ外になる。[MONITOR_BETA_OPERATION.md](../MONITOR_BETA_OPERATION.md)
  「4. データの取り扱い・分離」に記載の既知の割り切り）。この挙動は許容範囲と判断できます
  （69件はいずれも「招待制導入前の実験的な分析結果」であり、モニター企業のデータではないため）。
- [x] ~~本番の `alembic_version` が現在どのリビジョンか確認する~~ → 確認済み、
  **かつ重大な不整合を発見**。`alembic_version=a1f7ccac7a04`だが、次のマイグレーション
  `180b9b618513`が作成するはずの`verification_cases`等のテーブルが**既に物理的に存在**
  しています（`Base.metadata.create_all()`由来と推測）。**この状態のまま
  `alembic upgrade head`を実行すると、`180b9b618513`が`CREATE TABLE`で失敗する可能性が
  高いです。** モニターベータの3リビジョン適用前に、`alembic stamp`等でこの不整合を
  解消する方針を先に決める必要があります（DB書き込みを伴うため、本タスクでは未実施。
  詳細: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md) 6-1節）。

### migration実行順序の確認

- [ ] `docs/DEPLOYMENT.md`「実施順序（重要）」の原則どおり、**マイグレーション適用 →
  新コードデプロイ**の順で行う（逆順にすると本番が壊れる、という既存の教訓と同じ理由。
  今回の3リビジョン `f3a1c9d2e8b0` → `b7e2f4a1c3d5` → `d3f8a6b2c1e4` も例外ではない）。
- [ ] 3リビジョンは連続して適用する前提（途中で止める運用は想定していない。
  `b7e2f4a1c3d5`単体まで適用してデプロイを止めると、`monitor_sessions.token_hash`列が
  無い状態で新コードが動き、ログイン機能自体が落ちる）。

### seed実行可否判断

- [ ] 本番に対して `seed-plans` を実行してよいかは、単なる技術判断ではなく
  「価格・プラン内容が対外的に確定しているか」というビジネス判断を含む。
  `scripts/seed_data/pricing_plans.json` の内容（価格・クレジット量・マーケティング文言）を
  実際に本番へ出してよい内容までレビューしてから実行する。
- [ ] 技術的には既存プランを壊さない冪等操作だが（`code`キーのupsert、`is_active`は
  変更しない）、**初回の本番投入は他の変更と同様に計画的に行う**（詳細:
  [MONITOR_ACCOUNT_MANAGEMENT.md](../MONITOR_ACCOUNT_MANAGEMENT.md) §10）。

### スモークチェック項目（Phase 3実施直後に確認する内容を事前に決めておく）

- [ ] `GET /health` が200を返す
- [ ] `alembic current` が `d3f8a6b2c1e4 (head)` になっている
- [ ] `list-plans` で5プランが表示される（seed実行した場合）
- [ ] 最初の管理者アカウントでログインでき、`/api/v1/auth/me` が想定どおりの
  会社名・利用状況を返す
- [ ] 招待制導入前からの既存機能（`/api/v1/specs`一覧等）が認証必須になったことで
  想定通り401を返す（未ログイン状態でのアクセス）

### 切り戻し観点

- [ ] コードを戻す場合は「コードを先に戻す→その後にDBを`alembic downgrade`で戻す」の順序
  （`docs/DEPLOYMENT.md`の既存原則と同じ）。
- [ ] `d3f8a6b2c1e4 → b7e2f4a1c3d5 → f3a1c9d2e8b0` の順で1リビジョンずつ
  `downgrade`可能（本タスクのリハーサルで `downgrade base` までの全段ロールバック、
  および再度 `upgrade head` への復帰を隔離DBで確認済み。手順・ログは下記
  「リハーサル実施記録」参照）。
- [ ] `monitor_companies.monthly_credit_limit` はこのマイグレーションで
  `NOT NULL`からnullableに変わる。ダウングレード時はNULL行を既定値100で埋め戻してから
  `NOT NULL`制約を復元する（`f3a1c9d2e8b0`のdowngrade処理に実装済み）。
- [ ] 本番投入後に`seed-plans`で作成したプラン行自体を戻す一括コマンドは無い
  （`is_active=false`にするか、必要なら手動でDELETEする。plan削除の運用コマンド自体を
  意図的に用意していないため、切り戻しが必要な場合は個別対応になる）。

## Phase 3: 本番適用手順（実施する際のコマンド列。本タスクでは実行しない）

Phase 2のチェックが完了し、実施を決めたタイミングで、以下を順に実施してください。

```bash
# 0. バックアップ取得（DB方式に応じた既存手順に従う）

# 1. マイグレーション適用
cd backend
alembic current   # 適用前のリビジョンを記録しておく
alembic upgrade head

# 2. 新コードのデプロイ（systemdサービス再起動等、docs/DEPLOYMENT.mdの既存手順）

# 3. スモークチェック（Phase 2で決めた項目を確認）
curl https://campaignpilot.luvira.co.jp/health

# 4. プラン投入（ビジネス判断がOKであれば）
python ../scripts/manage_monitor_accounts.py seed-plans --dry-run
python ../scripts/manage_monitor_accounts.py seed-plans
python ../scripts/manage_monitor_accounts.py list-plans

# 5. 最初の管理者アカウントのブートストラップ
python ../scripts/manage_monitor_accounts.py create-company --name "自社（管理用）" --slug internal --limit 1000000
python ../scripts/manage_monitor_accounts.py create-user --company-slug internal --email <実際の管理者メール> --admin
```

以降のモニター企業追加はPhase 4（オンボーディング）に進みます。

## Phase 4: モニター1社目オンボーディング

手順そのものは [MONITOR_ACCOUNT_MANAGEMENT.md](../MONITOR_ACCOUNT_MANAGEMENT.md) の
「8. 新規モニター企業オンボーディングのクイックスタート」「8-1. ログイン案内テンプレート」
「8-2. 利用開始前チェックリスト」に集約してあるため、本ドキュメントでは重複させません。
Phase 3完了後は、そのままそちらの手順に進んでください。

## リハーサル実施記録（本タスクで実施・検証済み）

隔離した使い捨てSQLite DB（本番・開発中のDBとは無関係、リポジトリ外の一時ファイル）に対して、
以下を実際に一通り実行し、上記Phase 1〜4の手順どおりに再現できることを確認しました。

1. `alembic upgrade head`（baseline → 3リビジョン適用まで、一気に成功）
2. `seed-plans --dry-run` → `seed-plans`（実行）→ `list-plans`（5プランとも正しく投入）
3. 最初の管理者会社・管理者ユーザー作成（`create-company --limit 1000000` / `create-user --admin`)
4. モニター1社目作成（`--limit`省略）→ `assign-plan --plan-code monitor` →
   `create-user`（招待）→ `list-usage`（`plan:monitor, 0/100`と正しく表示）
5. 個別上書きの設定・解除（`set-limit --limit 150` → `list-usage`で`override, 0/150` →
   `clear-limit-override` → `list-usage`で`plan:monitor, 0/100`に復帰）
6. `monthly_credit_limit=0`（一時停止運用）の設定・解除（`list-usage`で`0/0`表示 → 解除で復帰）
7. 実際に発行した認証情報でのログイン確認（FastAPI経由、`/api/v1/auth/login` → 200、
   `session_token`発行）
8. `/api/v1/auth/me` が正しい会社名・`plan:monitor`ベースの利用状況を返すことを確認
9. 誤ったパスワードでのログインが401になることを確認（タイミング差対策の経路も通過）
10. `/api/v1/auth/logout` → 同一トークンでの以降のアクセスが401になることを確認
11. 上限0クレジットの状態で`/api/v1/auth/me`の`usage.limit_reached`が`true`になり、
    Streamlit UI側の警告表示のトリガーとなるフラグが正しく上がることを確認
12. `alembic downgrade base` → 全段ロールバック成功 → `alembic upgrade head`で復帰
    （ロールバック観点の実地検証）

### リハーサルで見つかり、その場で対応した軽微な不具合

- **CLI標準出力の文字化け**: Windows環境で `PYTHONIOENCODING` 未設定のまま
  `scripts/manage_monitor_accounts.py` を実行すると、コンソールの既定コードページ
  （cp932等）により日本語のプラン名・マーケティング文言が文字化けして表示されていた
  （DB内のデータ自体は正しいUTF-8で保存されており、表示のみの問題と確認済み）。
  `sys.stdout.reconfigure(encoding="utf-8")` をスクリプト冒頭に追加し、環境変数の
  設定に依存せず常に正しく表示されるよう修正した。
- **依存パッケージ未インストール時の誤誘導エラーメッセージ**: 誤ったPythonインタプリタ
  （`sqlalchemy`が未インストールの環境）で実行すると、実際の原因（依存パッケージ未インストール）
  ではなく常に「PYTHONPATHを設定してください」という固定メッセージが表示され、
  誤ったトラブルシュートに誘導されることが分かった。元の例外メッセージを併記するよう修正した。

### 未検証事項（本タスクの範囲外・今後の課題）

- ~~**本番DB（Postgres想定）でのマイグレーション適用**~~: 別タスクで隔離Postgres環境に
  対して同じ手順を実施済み。結果・差分・Postgres固有の注意点は
  [monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md) を参照
  （結論: 機能的な差分は見つからず、既存の軽微な冗長インデックスがSQLite・Postgres
  両方に共通して存在することを確認したのみ）。ただし本番相当のネットワーク経由・SSL接続
  経路は未検証のまま残っている。
- **実際の分析実行（`/api/v1/specs/analyze`）を通したクレジット消費**: LLM API呼び出しを
  伴うため、本タスクでは`/api/v1/auth/me`のクレジット残数表示までの確認に留めた
  （分析成功時の消費確定・失敗時の非消費は、既存の自動テスト
  `test_monitor_quota.py`で厳密に検証済み）。
- **実ブラウザ（Streamlit UI）でのオンボーディング一連の目視確認**: PR #91のレビュー対応時に
  実施済み（ログイン・サイドバー表示・ログアウト等）だが、本タスクで新規追加した
  ログイン案内テンプレート・利用開始前チェックリストの運用に沿った通し確認は未実施。
  実際にモニター1社目を受け入れる際に、この手順書どおりに進められるか併せて確認することを推奨する。
