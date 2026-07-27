# PostgreSQL移行 次タスク整理（[PR #81](https://github.com/nario0715masa0619-create/ad-insight-spec/pull/81) の続き）

[`docs/plans/postgresql_migration_readiness.md`](postgresql_migration_readiness.md)（PR #81）で
洗い出した「未確定事項」を、実行順が分かる粒度のタスクに分解したもの。ここでの役割は
**本番切替の実施ではなく、切替可能にするための不足条件を埋めること**。

本ドキュメントも readiness doc と同様、本番の現在の状態を断定していない
（未確認の事実は「確認する」タスクとして扱う）。

---

## A. 次タスク一覧（優先順位付き）

### Must（切替可否判断に必須。これが揃わない限り着手不可）

1. 本番環境の現状確認
2. 本番DB実体の確定（ローカル同居 or マネージドDB）
3. 本番Pythonバージョンと`psycopg2-binary`の整合確認
4. 本番DATABASE_URLの正本決定と`.env`管理ルール整備
5. 本番の既存データ件数確認（データ移行要否の判断）
6. ステージング相当のPostgres環境でのmigration成立確認

### Should（Mustが揃った後、切替実施前に整えておきたい）

7. 切替後smoke testの手順整備
8. rollback手順の明文化・演習
9. `docs/POSTGRES_MIGRATION.md`の実態への更新

### Nice-to-have（後回しでも切替判断は止まらない）

10. `init_postgres.sql` / `migrate_sqlite_to_pg.py`の扱い決定（9番に統合可）

---

## B. 各タスクの目的・完了条件・注意点

### 1. 本番環境の現状確認
- **目的**: 後続すべてのタスクの前提となる、本番の実際の状態（SQLite/Postgresどちらで動いているか、正常稼働しているか）を確定する。
- **完了条件**:
  - `systemctl status ad-insight-fastapi.service` / `ad-insight-streamlit.service`が`active (running)`であることを確認
  - `https://campaignpilot.luvira.co.jp/health`が200であることを確認
  - `/etc/ad-insight-spec/.env`の`DATABASE_URL`の**値の種別**（sqlite/postgres）を確認（値そのものは記録・共有しない）
- **注意点**: 読み取りのみ。設定変更・再起動は行わない。secretsをログや報告に残さない。

### 2. 本番DB実体の確定（ローカル同居 / 外部マネージドDB）
- **目的**: PostgreSQLをどこに置くかを決定する。readiness docではマネージドDBを「推奨の初期仮説」としたのみで未決定。
- **完了条件**: 選定理由・想定コスト・ネットワーク経路（VPC/Private IP等）が整理され、方針として確定している。
- **注意点**: タスク1の結果（本番の空きリソース・GCPプロジェクト権限）を踏まえてから判断する。

### 3. 本番Pythonバージョンと`psycopg2-binary`の整合確認
- **目的**: `requirements.txt`の`psycopg2-binary==2.9.9`が本番Pythonバージョンで実際にインストールできるかを確認する。
- **完了条件**: 本番Pythonバージョンを確認し、そのバージョン向けのホイールが存在するか（PyPIのファイル一覧、または本番venv相当環境での`pip install --dry-run`）で判定済み。不適合なら更新先バージョンを確定。
- **注意点**: `requirements.txt`は該当1行のみ更新する前提。全面再適用はしない。

### 4. 本番DATABASE_URLの正本決定と`.env`管理ルール整備
- **目的**: タスク2の結果を踏まえた実際の接続文字列を確定し、secretsの配置・更新手順を整備する。
- **完了条件**:
  - 接続情報（ホスト・ポート・DB名・ユーザー・パスワード）がSecret Manager等の安全な場所に配置されている
  - `.env`更新時の手順（誰が・いつ・どうやって反映し、サービス再起動が必要なこと）が文書化されている
  - `user:password@localhost`のようなプレースホルダ値が本番に残っていないことを確認する運用チェック項目がある
- **注意点**: `db/session.py`はプロセス起動時に一度だけ`DATABASE_URL`を読むため、`.env`変更だけでは反映されない（再起動必須）という点を手順に明記する。

### 5. 本番の既存データ件数確認（データ移行要否の判断）
- **目的**: 本番`ad_insights`テーブルにレコードがあるかどうかで、スキーマ移行だけで済むか、データ移行が必要かが変わる。
- **完了条件**: レコード件数を確認済み。0件ならこのタスクで完了（後続のデータ移行タスクは不要と確定）。1件以上あれば、移行スクリプトが必要と判断し、10番のタスクに接続する。
- **注意点**: 確認は読み取りのみ（`SELECT count(*)`相当）で、書き込み・削除は行わない。

### 6. ステージング相当のPostgres環境でのmigration成立確認
- **目的**: ローカル検証（PR #81で完了済み）を、本番相当のPostgresバージョン・設定で再現する。
- **完了条件**:
  - `alembic upgrade head`が成功し、`alembic current`が`d04670158813 (head)`になる
  - `verification_cases`のCHECK制約（`ck_verification_cases_asset_version_required_with_asset_id`）と、`verification_suggestion_evaluations`/`verification_followups`のFKが実際に作成されていることを確認
  - `downgrade`→再`upgrade`の往復が成立することを確認
- **注意点**: 本番`ad_insights`テーブルは`create_all()`由来でAlembic管理下に一度も入っていない点に注意。新規Postgres（空DB）に対して素直に`upgrade head`すればよいが、万一Postgres側に`ad_insights`が既に存在する状態から始める場合は`alembic stamp 5ce6bc069419`が先に必要（`a1f7ccac7a04`マイグレーションのdocstringに既存の注記あり）。

### 7. 切替後smoke testの手順整備
- **目的**: 切替直後に確認すべき項目（readiness doc E章に列挙済み）を、誰でも同じ手順で再現できる形にする。
- **完了条件**: `/health`・`/api/v1/specs`・verification CRUD一式・CSV出力・Streamlit 3タブ表示確認について、手順書またはチェックスクリプトが用意されている。
- **注意点**: 既存の`/api/v1/specs/*`のレスポンス形式・挙動を変更しない前提を崩さないよう、確認項目に「既存レスポンス形式が変わっていないこと」を含める。

### 8. rollback手順の明文化・演習
- **目的**: 切替に問題があった場合、即座にSQLiteへ戻せることを保証する。
- **完了条件**: readiness doc D章の手順を土台に、実際に非本番環境で1回切り戻しを演習し、所要時間と手順の過不足を確認済み。
- **注意点**: 演習は本番ではなくステージング/ローカルで行う。

### 9. `docs/POSTGRES_MIGRATION.md`の実態への更新
- **目的**: 「将来的にAlembicが導入されたら」という古い記述や、存在しないスクリプトへの参照を実態に合わせる。
- **完了条件**: 同ドキュメントが、既に導入済みのAlembicを前提とした記述になっており、`docs/plans/postgresql_migration_readiness.md`への参照が追加されている。
- **注意点**: readiness docと内容が重複しすぎないよう、`POSTGRES_MIGRATION.md`は「実行手順」、readiness docは「準備状況の整理」という役割分担を保つ。

### 10. `init_postgres.sql` / `migrate_sqlite_to_pg.py`の扱い決定
- **目的**: 現状「ドキュメントが参照しているが実体がない」状態を解消する。
- **完了条件**: 以下いずれかに決定し、実施済み:
  - (a) タスク5でデータ移行が必要と判明した場合、`migrate_sqlite_to_pg.py`を実際に作成する
  - (b) `init_postgres.sql`はAlembicが担うため不要と判断し、`docs/POSTGRES_MIGRATION.md`から参照を削除する（タスク9に統合）
- **注意点**: 独立Issueにせず、タスク5・9の一部として扱ってよい。

---

## C. Issue案（そのまま起票できる粒度）

> 実際にGitHub Issueとして起票はしていません。タイトル・本文の下書きです。

1. **本番環境の現在の稼働状態とDATABASE_URL設定を確認する**（Must）
   - 本文: `systemctl status`両サービス、`/health`、`.env`のDATABASE_URL種別（値は記録しない）を確認し、結果を記録する。読み取りのみ、変更なし。
2. **PostgreSQL実体（マネージドDB or VM同居）を決定する**（Must）
   - 本文: Issue #1の結果を踏まえ、コスト・運用負荷・ネットワーク構成を比較して方針を決定する。
3. **本番Pythonバージョンとpsycopg2-binaryの互換バージョンを確認・確定する**（Must）
   - 本文: 本番Pythonバージョンを確認し、`requirements.txt`の`psycopg2-binary`該当行のみ更新方針を決める。全面更新はしない。
4. **本番DATABASE_URLの正本を決定し、.env管理ルールを整備する**（Must）
   - 本文: Issue #2の結果を踏まえた接続文字列の確定、secrets配置、`.env`更新〜サービス再起動の手順書作成。
5. **本番の既存データ件数を確認し、データ移行要否を判断する**（Must）
   - 本文: `ad_insights`のレコード件数確認。0件ならクローズ、1件以上ならIssue #10へ接続。
6. **ステージングPostgres環境でAlembic migrationの成立を確認する**（Must）
   - 本文: Issue #2〜4の結果が固まった環境で、`upgrade head`・制約・FK・downgrade往復を再確認する。
7. **PostgreSQL切替後のスモークテスト手順を整備する**（Should）
   - 本文: readiness doc E章を土台に、手順書またはチェックスクリプトを作成する。
8. **PostgreSQL切替のロールバック手順を明文化し、非本番環境で演習する**（Should）
   - 本文: readiness doc D章を土台に、実際に1回切り戻しを試す。
9. **docs/POSTGRES_MIGRATION.md を実態に合わせて更新する**（Should）
   - 本文: Alembic導入済み前提への書き換え、存在しないスクリプト参照の整理、readiness docへの相互参照追加。

---

## D. 実施順のロードマップ

```
Phase 0（今すぐ着手可・本番への変更ゼロ）
  └─ Issue #1: 本番環境の現状確認

Phase 1（Phase 0の結果を踏まえ、並行して進められる意思決定）
  ├─ Issue #2: DB実体の決定
  └─ Issue #3: Python/psycopg2-binary整合確認

Phase 2（Phase 1の結果が必要）
  ├─ Issue #4: DATABASE_URL正本決定・.env管理ルール整備
  └─ Issue #5: 既存データ件数確認（→ 必要ならIssue #10相当のデータ移行作業）

Phase 3（Phase 2までが固まった環境で実施）
  └─ Issue #6: ステージングPostgresでのmigration成立確認

Phase 4（Phase 3と並行、または直後）
  ├─ Issue #7: smoke test手順整備
  └─ Issue #8: rollback手順の明文化・演習

Phase 5（いつでも着手可能だが、内容の正確性のため他が固まってから）
  └─ Issue #9: docs/POSTGRES_MIGRATION.md 更新
```

---

## E. 結論: 何から着手すべきか

**Issue #1（本番環境の現状確認）から着手する。**

理由:
- 後続のすべてのタスク（DB実体決定、DATABASE_URL決定、データ移行要否判断）が、
  この結果に依存している
- 内容は読み取りのみで、本番に一切変更を加えない（`systemctl status`、`/health`確認、
  `.env`の値の種別確認）ため、リスクゼロで即着手できる
- ここで「本番は実際にどういう状態か」を確定させて初めて、readiness docの
  未確定事項#1が解消され、Phase 1以降の意思決定に進める

Phase 0が完了するまでは、Phase 1以降のタスク（特にコードや設定を伴うもの）には着手しない。
