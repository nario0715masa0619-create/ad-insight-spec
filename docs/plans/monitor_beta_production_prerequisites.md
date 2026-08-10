# モニターベータ（PR #91）本番適用前提条件

## このドキュメントの目的

PR #91（招待制ログイン・クレジット制利用上限・`pricing_plans`）は`main`にマージ済みです。
本ドキュメントは、**アプリコード自体の準備は整った前提で、本番へ適用するために
何が確認・決定されれば良いか**を一覧化したものです。実際の本番接続・migration・
seed投入は本ドキュメント作成時点では**一切行っていません**。

先に結論を書きます。

> **本番適用の最大の論点は「Postgresの接続条件」ではなく、
> 「モニターベータをSQLiteのまま本番適用するか、Postgres移行を待つか」という方針決定です。**

理由は次章で説明します。

## 前提として発見した重要な事実（既存Issue #80系列との関係）

本ドキュメント作成にあたり、リポジトリ内の既存資料を確認したところ、
**本番のPostgres移行はPR #91とは独立に、既に[Issue #80](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/80)
として起票・分析が進んでいる未解決の課題**であることが分かりました。

- [Issue #80](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/80)
  「chore: CampaignPilot本番向けPostgreSQL移行の準備条件整理」（OPEN）
- [Issue #83](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/83)
  「chore: assess SQLite data migration scope for PostgreSQL cutover」（OPEN、未着手）
- [Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)
  「chore: clean up PostgreSQL migration docs and operational hygiene gaps」（OPEN、未着手）
- 関連docs: [postgresql_migration_readiness.md](./postgresql_migration_readiness.md) /
  [postgresql_migration_next_tasks.md](./postgresql_migration_next_tasks.md) /
  [postgresql_hosting_decision_memo.md](./postgresql_hosting_decision_memo.md) /
  [postgresql_cost_estimate_memo.md](./postgresql_cost_estimate_memo.md)

Issue #80の本文（過去の記録、本セッションでの再確認ではない）によれば:

- **本番は現在SQLite運用が正**（`/opt/ad-insight-spec/ad_insight.db`、確認時点で712KB）。
- **過去にPostgresへの切替を一度試みて障害になった実績がある**
  （`.env`がPostgreSQLを向いていたが、VM上にPostgreSQLサービスの実体が存在せず、
  `alembic upgrade head`がDB接続エラーで失敗）。その後SQLite運用に復旧している。
- Issue #80自身の「推奨方針」: **「当面はSQLiteを本番運用の正とする。PostgreSQL移行は
  別ブランチ・別検証で進める。障害復旧タスクと移行タスクを混ぜない。」**
- PostgreSQLの配置方針（VM同居 or Cloud SQL等マネージドDB）自体もまだ**未決定**
  （[postgresql_hosting_decision_memo.md](./postgresql_hosting_decision_memo.md)ではマネージドDBが
  「やや有力」とされているが、コスト・運用学習コストの検証待ちで断定はされていない）。
- Issue #83（データ移行規模の調査）・Issue #84（docs/運用衛生の整理）はいずれも
  チェックリストが未着手のまま残っている。

**この経緯を踏まえると、モニターベータのためだけに本番のPostgres移行を先に完了させるのは、
CLAUDE.mdの最優先方針「本番の安定運用を維持する」およびIssue #80自身の方針
（障害復旧タスクと移行タスクを混ぜない）と矛盾します。** 前回セッションで実施した
隔離Postgresでのリハーサル（[monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md)）は
「Postgresに移行するとなった場合に備えて機能面の不確実性を減らす」という意味では価値がありますが、
**モニターベータの本番適用そのものを、Postgres移行の完了を待つ理由にはすべきではない**、
というのが本ドキュメントの結論です。

## 推奨する2つの経路

### 経路A（推奨・短期）: 本番SQLiteのまま、モニターベータのmigrationを適用する

- PR #91の3リビジョン（`f3a1c9d2e8b0` / `b7e2f4a1c3d5` / `d3f8a6b2c1e4`）は、
  [monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)の
  リハーサル記録の通り、**SQLite上でupgrade/downgrade往復まで含めて動作確認済み**です。
  Postgresへの切替を待つ理由がありません。
- 本番のDB実体（SQLite）を変える必要が無いため、**Issue #80系列の未決定事項
  （Postgresの配置方針、psycopg2互換性、データ移行要否）から完全に独立して進められます。**
- この経路であれば、本ドキュメント末尾の「経路A用チェックリスト」だけを満たせば
  本番適用の判断ができます。

**更新（読み取り専用の本番SSH調査を実施）**: 経路A・Bのどちらを選ぶ場合でも、
共通して先に解決すべき**新たな重大事項**が見つかりました。本番の`alembic_version`が
実際のテーブル構成と食い違っています（詳細: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md) 6-1節）。
`alembic upgrade head`を素朴に実行すると失敗する可能性が高く、モニターベータの
migration適用前に必ず解消する必要があります。以降のチェックリストに反映しています。

### 経路B（将来・中長期）: Postgres移行（Issue #80系列）完了後に合流する

- Issue #80のチェックリストがすべて完了し、本番が実際にPostgresへ切り替わった後、
  モニターベータの3リビジョンを含む完全なmigrationチェーンが、その本番Postgres上で
  再度動作確認される、という順序になります。
- 隔離Postgresでのリハーサル（[monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md)）は
  すでに完了しているため、**Postgres移行が実現した時点での追加の不確実性は小さい**
  はずです（機能的な差分は見つかっていないため）。
- ただし、経路Bは本ドキュメントの対象外にあるIssue #80系列の完了が前提であり、
  完了時期は本タスクの範囲では見積もれません。

**以降のチェックリストは経路Aを主軸とし、経路B固有の事項は別セクションに分離しています。**

---

## 1. DB / 接続

### 経路A（SQLiteのまま）向け

| 項目 | 状態 | 備考 |
|---|---|---|
| 本番DBの実体確認 | **確認済み**（本タスクで読み取り専用SSHにより直接確認） | SQLite、`/opt/ad-insight-spec/ad_insight.db`（729,088 bytes、権限0777） |
| `DATABASE_URL`の管理方法 | 変更不要 | 現状の`.env`設定のまま。新しい接続文字列を用意する必要がない |
| SSL要否 | 該当なし | SQLiteのためネットワーク接続自体が発生しない |
| 接続ユーザー権限 | 該当なし | ファイルベースのため、OSユーザーの読み書き権限のみ関係する |
| migration実行権限 | **確認済み** | 本タスクで実際に`gcloud compute ssh`でVMへ接続できることを確認済み。sudo権限も利用可能 |
| seed実行権限 | 確認済み | 同上 |
| **Alembic管理状態と実スキーマの整合性** | **問題を発見（重大）** | `alembic_version`が`a1f7ccac7a04`のままだが、次のマイグレーション`180b9b618513`が作るはずの`verification_cases`等のテーブルが既に存在する（`create_all()`由来と推測）。素朴に`alembic upgrade head`すると失敗する可能性が高い。詳細: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md) 6-1節 |

### 経路B（Postgres）向け（Issue #80系列に委譲・本ドキュメントでは深追いしない）

| 項目 | 状態 | 備考 |
|---|---|---|
| Postgresの配置方針（VM同居 / Cloud SQL） | **未決定** | [postgresql_hosting_decision_memo.md](./postgresql_hosting_decision_memo.md)でマネージドDBがやや有力だが断定なし |
| 接続方式・SSL | 未確認 | 配置方針が決まってから確定する |
| psycopg2-binaryの互換性 | **訂正: リスクは低い**（下記参照） | 本番venvには実際には`psycopg2-binary==2.9.12`が既に導入済み（`requirements.txt`のピン値`2.9.9`とは不一致だが、動作するバージョンは既に入っている） |
| migration実行権限・seed実行権限 | 確認済み | 経路Aと同じVM・同じSSHアクセスで足りる |

**訂正（本タスクで本番venvを直接確認）**: 前回、PyPI上のメタデータのみから
「`psycopg2-binary==2.9.9`は本番Python 3.13向けホイールが無いため経路Bでは更新必須」と
記載しましたが、**本番venv（`/opt/ad-insight-spec/venv`）を実際に確認したところ、
既に`psycopg2-binary==2.9.12`がインストール済み**でした（`requirements.txt`・
未コミットの`setup.sh`はどちらも`2.9.9`を指定しており、実態と食い違っています。
おそらくIssue #80が言及する過去のPostgres切替試行の際に手動で導入されたまま残ったものです）。
**経路Bを選ぶ場合のpsycopg2-binary起因のブロッカーは、想定より小さいことが分かりました。**
ただし`requirements.txt`・`setup.sh`と実態の乖離自体は[Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)の
運用衛生課題として解消することを推奨します。詳細: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md) 6-3節。

## 2. データ

| 項目 | 状態 | 備考 |
|---|---|---|
| 既存SQLiteデータの有無 | **確認済み**（本タスクで読み取り専用確認、Issue #83を先取り） | `ad_insights`が69件。`verification_*`系テーブルは0件（後述のAlembic不整合の一因） |
| データ移行要否 | 経路Aでは**不要** | SQLiteのまま追加テーブル（`monitor_*`, `pricing_plans`, `credit_usage_logs`）を作成するだけであり、既存の`ad_insights`データはそのまま残る（`company_id`は`NULL`のまま。[MONITOR_BETA_OPERATION.md](../MONITOR_BETA_OPERATION.md)記載の既知の割り切り） |
| 初回導入時に空でよいか | **空でよい** | `monitor_*`系テーブルは新規テーブルのため、初回は必然的に空。既存の`ad_insights`データへの影響はスキーマ追加のみ |
| backup方針 | **確認済み（問題を発見）** | 自動バックアップは存在せず、約31日前・古いスキーマの手動バックアップが1件のみ、同一ディスクに保存。詳細・リスク整理: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md) |
| rollback時の戻し方 | **確認済み（手順化済み。ただしAlembic不整合に注意）** | [monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md) Phase 2「切り戻し観点」に記載。SQLite・Postgres両方でdowngrade往復をリハーサル済みだが、これは「クリーンな状態からのリハーサル」であり、本番の`alembic_version`不整合を解消せずに同じ手順をそのまま適用できるかは未検証 |

## 3. アプリ運用

| 項目 | 状態 | 備考 |
|---|---|---|
| 初回admin作成手順 | **確認済み・手順化済み** | [MONITOR_ACCOUNT_MANAGEMENT.md](../MONITOR_ACCOUNT_MANAGEMENT.md) §1、SQLite/Postgres両方でリハーサル済み |
| 初回monitor company作成手順 | **確認済み・手順化済み** | 同§8、§8-1、§8-2 |
| plan適用方針 | **確認済み** | `monitor`プランを基本に割り当てる方針。§2-2に運用ルールあり |
| overrideの運用方針 | **確認済み** | §2-2に一時増枠・特殊契約時の使い分けルールあり |
| 0クレジット運用の扱い | **確認済み** | §2-2に記載、SQLite/Postgres両方で`limit_reached`挙動をリハーサル済み |
| ログイン案内の方法 | **確認済み・テンプレート化済み** | §8-1（本番適用前提条件確認タスクの前段で追加済み） |

**アプリ運用面は経路A・経路Bのどちらでも共通**であり、既にリハーサル・文書化が
完了しています。本番適用の判断において、この領域はボトルネックになりません。

## 4. スモークチェック

本番適用直後に確認すべき項目です。経路Aの場合、以下がそのまま使えます
（Postgres特有の追加項目は不要）。

- [ ] `GET /health` が200
- [ ] `alembic current` が `d3f8a6b2c1e4 (head)` になっている
- [ ] 招待制導入前の既存機能（`GET /api/v1/specs`等）が、未ログイン時に401を返す
      （認証必須化の意図した挙動）
- [ ] `list-plans`（`seed-plans`を実行した場合）で5プランが表示される
- [ ] 最初の管理者アカウントでログインでき、`/api/v1/auth/me`が想定通りの
      会社名・利用状況を返す
- [ ] 0クレジット時に`usage.limit_reached=true`となる
- [ ] 既存の`ad_insights`関連エンドポイントが、招待制導入前と同じレスポンス形式で
      動作する（company_idがNULLの既存データも一覧から除外されるだけで、
      エラーにはならないこと）

分析実行（`/api/v1/specs/analyze`）そのもののスモークは、LLM API呼び出しを伴うため
本ドキュメントの範囲では手順化のみに留めます（実行は本番適用作業時に行う）。

---

## 確認済み / 未確認 まとめ

### 確認済み

- SQLite上でのmigration/downgrade往復、seed冪等性、admin/company/plan/override運用、
  login/`/me`/logout、0クレジットブロック（[monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md)）
- 隔離Postgres上での同等の動作（機能差分なし。[monitor_beta_postgres_rehearsal.md](./monitor_beta_postgres_rehearsal.md)）
- モニターベータのアプリ運用手順一式（admin作成〜オンボーディングまで）
- **本番が現在SQLite運用中であること**（本タスクで読み取り専用SSHにより直接確認。
  `/opt/ad-insight-spec/ad_insight.db`、729,088 bytes）
- **本番`ad_insights`の既存件数（69件）**（本タスクで確認、Issue #83を先取り）
- **本番のバックアップ運用状況**（自動化無し、31日前の手動バックアップ1件のみ、
  同一ディスク保存。詳細: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md)）
- **migration/seed実行者の本番アクセス権限**（本タスクで実際にSSH接続・sudo利用を確認）
- **本番venvのpsycopg2-binaryは実際には2.9.12が導入済み**（前回整理した2.9.9起因の
  互換性リスクは訂正。`requirements.txt`との不一致自体はIssue #84相当の課題として残る）
- **本番デプロイ済みコードがPR #79時点（`9c6da0f`）で止まっており、PR #91は未デプロイ**
  （想定通りだが本タスクで直接確認）

### 未確認

- **本番の`alembic_version`（`a1f7ccac7a04`）と実スキーマ（verification系テーブルが
  既に存在）の不整合をどう解消するかの具体的な方針**（新規発見・最重要）
- バックアップ運用を今後どう設計すべきか（頻度・世代数・保存先の方針の意思決定）
- 復元手順の正式な文書化・演習
- 本番ディスク空き容量への影響（確認時点で使用率80%、空き約1.9GB。新規テーブル自体は
  小さいためほぼ無視できる想定だが未検証）
- Postgres移行の完了時期（経路Bを選ぶ場合。Issue #80系列に委譲）

---

## 経路A用チェックリスト（本番適用判断に必要な最小セット）

- [x] ~~本番SQLiteのバックアップ運用（頻度・自動化）を確認する~~ → 確認完了。
      自動化無し、31日前の古いバックアップ1件のみ（[詳細](./monitor_beta_production_backup_status.md)）。
      **本番適用前に、最低でも適用直前の手動バックアップ取得を推奨**（実行はしていません）。
- [x] ~~本番`ad_insights`の既存件数を確認する~~ → 確認完了。69件。
- [x] ~~migration/seed実行者の本番アクセス権限を確認する~~ → 確認完了。SSH・sudo利用可能。
- [ ] **【新規・最優先】本番の`alembic_version`（`a1f7ccac7a04`）と実スキーマの不整合
      （verification系テーブルが`create_all()`由来で既に存在）を解消する方針を決める**
      （`alembic stamp`等が候補だが、DB書き込みを伴うため本タスクでは実施していない。
      これを解消しないまま`alembic upgrade head`すると失敗する可能性が高い）
- [ ] 本番適用直前の手動バックアップを取得する（実行判断はユーザー側で）
- [ ] 本番適用のタイミング（メンテナンス時間帯等）を決める
- [ ] [monitor_beta_post_merge_runbook.md](./monitor_beta_post_merge_runbook.md) Phase 3の
      手順に従って本番へ適用する（ただし上記Alembic不整合の解消が前提）
- [ ] 上記「スモークチェック」を実施する

## 経路B用チェックリスト（Postgres移行を選ぶ場合）

Issue #80のチェックリストをそのまま参照してください。加えて:

- [x] ~~`requirements.txt`のpsycopg2-binaryを本番Pythonバージョンに適合するバージョンへ更新する~~
      → 訂正: 本番venvには既に動作する`2.9.12`が導入済みのため、緊急の作業ではない
      （`requirements.txt`との表記不一致はIssue #84相当で解消を推奨）
- [ ] 経路Aと共通の「Alembic不整合の解消」を先に行う
- [ ] Issue #80の切替完了後、モニターベータの3リビジョン（`f3a1c9d2e8b0`〜`d3f8a6b2c1e4`）を
      含む完全なmigrationチェーンを、実際の本番相当Postgres環境で再確認する

---

## 次タスク候補（Issue化しやすい粒度、ドラフトのみ・起票はしていません）

1. **【最優先・新規】本番のAlembic管理状態の不整合を解消する方針を決め、実施する**（Must、経路A・B共通）
   - `alembic_version=a1f7ccac7a04`のまま、`180b9b618513`が作るはずのverification系
     テーブルが既に存在する状態を解消する。候補は`alembic stamp 180b9b618513`（さらに
     `d04670158813`まで）だが、実際のテーブル定義とマイグレーションが完全に一致しているかの
     確認が先に必要。DB書き込みを伴うため、本タスクでは実施していない。
2. **本番適用直前の手動バックアップ取得を運用に組み込む**（Must、経路A）
   - 最低限、モニターベータのmigration適用前に1回、`cp`によるファイルコピーで
     バックアップを取得する運用を、実際の適用作業の一部として組み込む。
3. **モニターベータの本番適用タイミングを決定する**（Must、経路A）
   - メンテナンス時間帯、関係者への事前周知が必要か等。
4. **本番の自動バックアップ運用を整備する**（Should、経路A・B共通）
   - cron/systemd timerいずれかで日次バックアップを自動化し、複数世代保持する。
     可能ならVM外（GCSバケット等）への保存も検討する。
5. **`requirements.txt`/`setup.sh`のpsycopg2-binary表記を実態（2.9.12）に合わせる**（Should、Issue #84相当）
   - 緊急ではないが、ドキュメントと実態の乖離を放置しない。
6. **VM上のuntrackedファイル（`setup.sh`, `current-freeze.txt`, `=2.2.0`等）の扱いを決める**（Should、Issue #84相当）
7. **Issue #87（事業検証パイロット）とモニターベータの連携を検討する**（Should）
   - Issue #87は3〜5件の実案件でCampaignPilotの価値を検証する計画だが、
     現状の計画docsは招待制ログイン・会社単位分離が導入される前に書かれている。
     モニターベータの会社作成・招待フローが、そのままパイロット参加者への
     アカウント発行手段として使える可能性が高く、連携を検討する価値がある。

---

## 今回実施したこと・スコープ外として残したもの

**本タスクで新たに実施したこと**: 本番VMへの読み取り専用SSH接続による、DB実体パス・
バックアップ運用状況・`ad_insights`件数・Alembic管理状態・デプロイ済みコードのバージョン・
psycopg2-binary実態の直接確認（詳細: [monitor_beta_production_backup_status.md](./monitor_beta_production_backup_status.md)）。
DB更新・`.env`編集・バックアップ設定変更・サービス再起動・手動バックアップ/復元実行は
一切行っていません。

**スコープ外として残したもの**:
- Alembic不整合の実際の解消（`alembic stamp`等、DB書き込みを伴うため）
- Issue #80/#83/#84自体の作業実施（既存の別トラックのため、本タスクでは分析の参照のみ）
- Postgres移行の実施判断そのもの（経路Aか経路Bかは、本ドキュメントの整理を踏まえて
  ユーザー側で最終判断することを想定）
- GitHub Issueの新規起票（「次タスク候補」はドラフトに留め、実際の起票はしていません）
- 本番の自動バックアップ運用の実装（設定変更を伴うため）
