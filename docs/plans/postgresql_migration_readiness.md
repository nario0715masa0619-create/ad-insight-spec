# PostgreSQL移行 準備状況メモ（2026-07-27時点）

## このドキュメントについて

CampaignPilot（Ad-Insight-Spec）を SQLite から PostgreSQL へ移行するための、
準備状況の整理と実施可否判断。**本番切替は今回のスコープ外**。既存の
[`docs/POSTGRES_MIGRATION.md`](../POSTGRES_MIGRATION.md) は Alembic 導入前に書かれた
古い手順書で、現状と食い違う記述（後述）があるため、正確な現状整理として本ドキュメントを作成した。

**追記（後続タスクでの確認事項）**: 「未確定事項#2」（本番Pythonバージョンと
`psycopg2-binary`の整合）について、後続の
[monitor_beta_production_prerequisites.md](./monitor_beta_production_prerequisites.md)
（招待制モニターベータPR #91の本番適用前提整理タスク）で、PyPI上のパッケージ
メタデータを確認したところ、現在`requirements.txt`が固定する`psycopg2-binary==2.9.9`は
**Python 3.13向けホイール（`cp313`）が存在しない**ことを確認した（3.14だけでなく
3.13でも本ドキュメント記載の懸念が該当する）。本番Pythonが3.13.5という記録
（[postgresql_hosting_decision_memo.md](./postgresql_hosting_decision_memo.md)参照）が正しければ、
`requirements.txt`のピン値と実際に動くバージョンが一致していないことになる。

**訂正（さらに後続の本番SSH調査で判明）**: 上記はPyPIのメタデータのみに基づく懸念だったが、
本番venv（`/opt/ad-insight-spec/venv`）を読み取り専用で直接確認したところ、**実際には
`psycopg2-binary==2.9.12`が既にインストール済み**であることが分かった（`requirements.txt`の
ピン値`2.9.9`とは異なるが、動作するバージョンは既に入っている）。そのため、
**Postgres移行時に`requirements.txt`の更新が「必須」とまでは言えず、想定していたリスクは
低い**。`requirements.txt`・未コミットの`setup.sh`の表記と実態の乖離自体は、
移行そのもののブロッカーではなく[Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)
（運用衛生課題の整理）の対象として解消することを推奨する。詳細:
[monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md) 6-3節。

**重要な前提の注記**: 本ドキュメントの検証内容は、すべてローカルの検証用環境
（ローカルWindows機に新規インストールしたPostgreSQL 16、または開発用SQLite）で
行ったものであり、本番VM（34.84.24.83）には一切アクセスしていない。本番の実際の
状態（SQLite運用中か、Postgresが動いているか、直近の障害があったか等）は、
本ドキュメント作成時点で確認できていない。**本番切替の実施前には、必ず
`systemctl status ad-insight-fastapi.service` 等で本番の実際の状態を確認すること。**

---

## 決定事項（検証済み・確定している事実）

- **db/session.py の DATABASE_URL 対応は完了・main にマージ済み**（PR #78）。
  `DATABASE_URL` 環境変数（未設定時は `sqlite:///./ad_insight.db`）を
  `app.config.get_settings()` 経由で正しく参照する。SQLite/Postgresで
  `connect_args` を出し分けるロジックも単体テスト込みで検証済み。
- **Alembicマイグレーション4本は、ローカルPostgreSQL 16に対してエラーなく適用できる**
  （`5ce6bc069419` → `a1f7ccac7a04` → `180b9b618513` → `d04670158813`）。
  `upgrade head` → `downgrade` → 再 `upgrade` の往復も確認済み。
- **verification機能（案件・提案評価・followup・CSV出力）は、実PostgreSQL接続下で
  一連のCRUDが問題なく動作する**（一覧・詳細・提示後評価・CSV出力すべて確認）。
- **`asset_id`指定時に`asset_version`が無いと422（Pydanticバリデータ+DB CHECK制約の
  二重防御）で拒否される**ことをPostgres上でも確認済み。RequestValidationErrorハンドラの
  500化バグ（PR #79で修正済み）も、Postgres接続下で422が正しく返ることを確認済み。
- **既存の`/api/v1/specs/*`への影響なし**（一覧・詳細取得ともPostgres接続下で正常動作）。
- **`requirements.txt`の`psycopg2-binary==2.9.9`は、Python 3.14環境では
  インストール自体が失敗する**（3.14向けホイールが無く、ソースビルドも
  `pg_config`未検出等でエラー）。`psycopg2-binary==2.9.12`は同環境で
  問題なくインストール・動作する（ローカル検証で確認）。
- `docs/POSTGRES_MIGRATION.md` が参照している `scripts/init_postgres.sql` と
  `scripts/migrate_sqlite_to_pg.py` は、**リポジトリ上に実在しない**
  （検索して不在を確認済み）。同ドキュメントは「将来的にAlembicが導入されたら」という
  書き方のままだが、Alembicは既に導入済みであり、この記述は古い。

## 未確定事項（本番切替前に必ず確認が必要）

1. **本番VMの現在の実際の状態**（SQLiteかPostgresか、正常稼働しているか）。
   本ドキュメントは一切前提としていない。
2. **本番VMのPythonバージョン**。`psycopg2-binary`のバージョン選定に直結する
   （3.9.9の可否・3.9.12以降への更新要否）。
3. **PostgreSQLの実体をどこに置くか**（本番VMへのローカル同居インストールか、
   Cloud SQL等のマネージドDBか）。これによって接続情報・ネットワーク経路・
   バックアップ運用が大きく変わるため、他の全項目より先に決める必要がある。
4. **本番`ad_insights`テーブルの現在の中身**（既存の分析結果データがどれだけあるか）。
   これが空でなければ、スキーマ移行だけでなく**データ移行**が必要になる
   （後述の通り、移行スクリプトは現状存在しない）。
5. **本番の`/etc/ad-insight-spec/.env`に、過去にPostgres用の仮設定やサンプル値が
   残っていないか**。

## 推奨方針

- PostgreSQLの実体は、**まずマネージドDB（Cloud SQL for PostgreSQL等）を第一候補として検討**する。
  理由: 本番VM上にPostgresをローカル同居させると、CLAUDE.md記載の「本番の安定運用維持」という
  最優先方針に対し、パッチ適用・バックアップ・ディスク管理まで自前運用のスコープに入り、
  運用負荷が一段上がる。マネージドDBであれば、バックアップ・可用性の大半を委譲できる。
  ただし、コスト・ネットワーク構成（VPC/Private IP等）は別途整理が必要なため「決定」ではなく
  「推奨の初期仮説」として扱う。
- `psycopg2-binary`は、**本番Pythonバージョンを確認した上で、そのバージョンに実在するホイールを
  持つ最小バージョンに固定**する（`requirements.txt`は該当1行のみ更新。全面再適用はしない）。
- データ移行が必要な場合は、`docs/POSTGRES_MIGRATION.md`が参照するだけで実在しない
  移行スクリプトを新規に用意する（案件数・分析結果数から見て、シンプルなPython製
  SQLite→Postgresコピースクリプトで十分な規模と想定されるが、本番の実データ量の
  確認が先）。
- 本番切替を行う際は、**`alembic upgrade head`をいきなり実行しない**。既存の
  `a1f7ccac7a04_add_asset_data_and_evaluation_data_columns.py`等のdocstringに明記の通り、
  本番の`ad_insights`テーブルは`create_all()`で作られた実体であり、Alembicの管理下に
  一度も入っていない。そのままPostgres上で`upgrade head`すると、baseline migration
  (`5ce6bc069419`)が`CREATE TABLE ad_insights`を試みて衝突するか、あるいはPostgres上に
  テーブルがまだ無ければ素直に通ってしまうため要注意（後述のチェックリスト参照）。

## 禁止事項

- 本番DBに対する破壊的操作（テーブル削除・データ削除・強制的なスキーマ変更）を、
  切替計画の確定・関係者確認なしに実行しない。
- `requirements.txt`全体の一括更新はしない（`psycopg2-binary`1行のみに限定）。
- `/api/v1/specs/*`の挙動・レスポンス形式を変更しない。
- 本番サービス停止を伴う作業は、実行前に確認を取ってから行う（勝手に`systemctl stop`等をしない）。
- サンプル値・プレースホルダのパスワード（`user:password@localhost`等）を本番`.env`に
  残したまま運用しない。

---

## A. PostgreSQL移行準備メモ

### DB実体の選択肢と整理

| 選択肢 | メリット | デメリット | 必要な追加情報 |
|---|---|---|---|
| マネージドDB（Cloud SQL for PostgreSQL等） | バックアップ・パッチ・可用性を委譲できる。CLAUDE.mdの「安定運用優先」方針と整合 | VPC/Private IP構成、コスト、GCPプロジェクトの権限整理が必要 | 接続先ホスト、認証方式（IAM認証 or パスワード認証）、ネットワーク経路（Private Service Connect等） |
| 本番VMへのローカル同居インストール | 追加インフラ不要、既存`docker-compose.yml`のpostgresサービス定義がそのまま使える | VM自体のリソース圧迫、バックアップ・パッチ運用が自前になる | ディスク容量、メモリ余裕、バックアップ用cron等の設計 |

現時点では**マネージドDBを推奨の初期仮説**とするが、最終判断は未確定事項#3の
確認後に行うこと。

### 接続設定の要件

- 最終的に本番`/etc/ad-insight-spec/.env`に置く`DATABASE_URL`は、下記いずれかの形式:
  ```
  # ローカル同居の場合
  DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<dbname>
  # マネージドDB(Cloud SQL, Private IP接続の場合)
  DATABASE_URL=postgresql://<user>:<password>@<private-ip>:5432/<dbname>
  ```
- `<user>`/`<password>`は`docker-compose.yml`にある`user`/`password`のような
  プレースホルダのまま本番に置かないこと。実際の強固なパスワードを生成し、
  GCP Secret Manager等の管理下に置くことを推奨（CLAUDE.mdの既存方針と整合）。
- SQLiteとPostgresを安全に切り替える運用ルール:
  1. 切替前に必ず`DATABASE_URL`の現在値を記録しておく（切り戻し用）。
  2. `.env`編集後は、必ず`systemctl restart ad-insight-fastapi.service`が必要
     （`db/session.py`はプロセス起動時に一度だけ`DATABASE_URL`を読むため、
     `.env`だけ書き換えてもプロセス再起動なしには反映されない）。
  3. 切替直後は`/health`だけでなく、`/api/v1/specs`が実際にPostgres側のデータを
     返しているか（空か、期待通りの件数か）まで確認する。

### Python / psycopg2-binary 方針

- 本番Pythonバージョンを確認してから、そのバージョンに対応するホイールを持つ
  `psycopg2-binary`の最小バージョンを選ぶ。目安（今回のローカル検証で確認した範囲）:
  - Python 3.14系: `psycopg2-binary>=2.9.10`程度が必要（`2.9.9`はホイール無し、
    `2.9.12`で動作確認済み）。
  - Python 3.12以下: 既存の`2.9.9`のままで問題ない可能性が高い（要現地確認。
    PyPIのホイール一覧で当該Pythonバージョン向けの`cp3x`ホイールが存在するか
    確認すればよい）。
- 既存venvを壊さない導入方法:
  ```bash
  # 本番venv内で、まずドライランで解決可否だけ確認する
  pip install --dry-run psycopg2-binary==<候補バージョン>
  # 問題なければ requirements.txt の該当1行だけ更新してから通常インストール
  ```
  `pip install -r requirements.txt`の全面再実行はしない（他の依存関係の
  意図しないバージョン変更を防ぐため）。

---

## B. 本番切替の前提条件チェックリスト

切替作業に着手する前に、すべて✅にすること。

- [ ] 本番VMの現在の実際の状態を`systemctl status ad-insight-fastapi.service`
      `systemctl status ad-insight-streamlit.service`で確認済み
- [ ] 本番の`/health`（`https://campaignpilot.luvira.co.jp/health`）が200であることを確認済み
- [ ] 本番Pythonバージョンを確認済み（`python3 --version`）
- [ ] 上記バージョンに適合する`psycopg2-binary`のバージョンを確定済み
- [ ] PostgreSQLの実体（マネージドDB or ローカル同居）を決定済み
- [ ] 接続情報（ホスト・ポート・DB名・ユーザー・パスワード）を確定し、
      Secret Manager等の安全な場所に配置済み
- [ ] 本番`ad_insights`テーブルの現在のレコード件数を確認済み（0件ならデータ移行不要）
- [ ] レコードが存在する場合、データ移行スクリプトを用意し、非本番環境で
      テスト移行を実施済み
- [ ] 新しいPostgresインスタンス上で、**空の状態から**
      `alembic upgrade head`が通ることをステージング環境で確認済み
      （このドキュメント作成時点でローカル検証は完了しているが、
      本番相当のPostgresバージョン・設定でも再確認すること）
- [ ] `verification_cases`のCHECK制約・全テーブルのFKがステージングで
      作成されていることを確認済み
- [ ] バックアップ（SQLiteファイルのコピー）を取得済み
- [ ] 切り戻し手順（本ドキュメントD章）を関係者が把握済み
- [ ] 切替作業の実施タイミングについて合意が取れている（サービス影響を伴うため）

---

## C. 切替手順案（実施前に必ず確認を取ること。ここに記載しても自動実行はしない）

1. **事前バックアップ**
   ```bash
   cp /opt/ad-insight-spec/ad_insight.db /opt/ad-insight-spec/ad_insight.db.backup.$(date +%Y%m%d_%H%M%S)
   ```
2. **psycopg2-binaryの導入**（本番venv内、確定したバージョンで）
   ```bash
   pip install psycopg2-binary==<確定したバージョン>
   ```
3. **PostgreSQL側の準備**（DB・ユーザー作成。マネージドDBの場合はコンソール側で実施）
4. **`.env`更新**（`/etc/ad-insight-spec/.env`の`DATABASE_URL`を新しいPostgres接続文字列に変更）
5. **Alembicのベースライン揃え**（既存データがある＝`ad_insights`テーブルに
   レコードがある場合、新しいPostgres側は空なので、baseline migrationから
   素直に`upgrade head`してよい。逆に、もし何らかの理由でPostgres側に
   既にad_insightsテーブルが存在する場合は、`upgrade head`の前に
   `alembic stamp 5ce6bc069419`が必要 — `a1f7ccac7a04`のマイグレーションファイルの
   docstringに明記された既存の注意点）
   ```bash
   cd backend
   alembic upgrade head
   alembic current   # d04670158813 (head) になっていることを確認
   ```
6. **データ移行**（`ad_insights`にレコードがある場合のみ。移行スクリプトは
   本タスクでは未作成 — 必要になった時点で別途用意する）
7. **サービス再起動**
   ```bash
   sudo systemctl restart ad-insight-fastapi.service
   sudo systemctl restart ad-insight-streamlit.service
   ```
8. **スモークテスト**（E章のリストを参照して実施）
9. 問題なければ完了。問題があれば直ちにD章の切り戻し手順を実施。

---

## D. 切り戻し手順案

1. `/etc/ad-insight-spec/.env`の`DATABASE_URL`を、切替前に記録しておいた元の値
   （SQLite）に戻す
2. サービス再起動
   ```bash
   sudo systemctl restart ad-insight-fastapi.service
   sudo systemctl restart ad-insight-streamlit.service
   ```
3. `/health`・`/api/v1/specs`が正常応答することを確認
4. Postgres移行中に本番SQLite側へ新規に書き込まれたデータがあれば
   （切替作業中も並行してサービスが動いていた場合）、その差分をどう扱うかを
   個別に判断する（通常は「切替作業は書き込みの少ない時間帯に短時間で行い、
   差分は発生させない」運用を推奨）
5. 切り戻し後、Postgres側は次回の切替まで温存するかどうかを判断する

---

## E. スモークテスト項目（切替後、最低限これを実施する）

- `GET /health`
- `GET /api/v1/specs`
- `GET /api/v1/specs/{asset_id}`（既存データがあれば1件）
- verification案件作成（`POST /api/v1/verification/cases`）
- `asset_id`のみ指定時に422になること
- `asset_id`+`asset_version`指定時に正常保存できること
- 提案評価保存（`POST /api/v1/verification/cases/{id}/suggestions`）
- followup保存（`PUT /api/v1/verification/suggestions/{id}/followups/week_2`等）
- CSV出力（`GET /api/v1/verification/export.csv`）
- Streamlit UIで「新規分析」「保存済み結果」「検証」の3タブとも表示崩れがないこと

いずれも、今回のローカル検証（本ドキュメント「決定事項」参照）で手順自体は
確立済み。本番/ステージングでもほぼ同じ手順で再実施できる。

---

## F. 現時点での判断: **本番切替はまだ実施不可**

理由: 「未確定事項」の1〜5がすべて未確認のため。特に#1（本番の実際の状態）と
#3（DB実体の置き場所）が確定しない限り、切替計画のC章・D章を本番向けに
確定させることができない。

**次に必要なアクション**（優先順）:
1. 本番の実際の状態を確認する（SQLiteかPostgresか、正常稼働しているか）
2. 本番Pythonバージョンを確認する
3. PostgreSQLの実体（マネージドDB or ローカル同居）を決定する
4. 上記が揃った時点で、本ドキュメントのB章チェックリストを埋めていく

これらが揃えば、C章・D章の手順を本番向けに具体化し、実施可否を再判断できる。
