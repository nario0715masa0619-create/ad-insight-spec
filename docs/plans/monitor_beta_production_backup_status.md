# 本番SQLiteバックアップ運用状況の確認（読み取り専用調査）

## この調査について

[monitor_beta_production_prerequisites.md](./monitor_beta_production_prerequisites.md)の
経路A（本番SQLite継続でモニターベータを適用する）チェックリストのうち、
「本番SQLiteのバックアップ運用（頻度・自動化）を確認する」を実施した記録です。

**本番VMへは読み取り専用コマンドのみで接続し（`gcloud compute ssh`）、DB更新・`.env`編集・
バックアップジョブ設定変更・`systemctl restart`・手動バックアップ実行・手動復元実行・
ファイル削除/移動は一切行っていません。**

## 1. authoritativeなSQLite DB実体パス

- `DATABASE_URL=sqlite:////opt/ad-insight-spec/ad_insight.db`
  （`/etc/ad-insight-spec/.env`、`ad-insight-fastapi.service`の`EnvironmentFile`から参照）
- ファイル詳細（確認時点）:
  - サイズ: 729,088 bytes（約712KB。[Issue #83](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/83)記載の推定値と整合）
  - 権限: `0777`（`rwxrwxrwx`）— [Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)が
    既に指摘している既知の問題と一致（本ドキュメントでは変更していません）
  - 所有者: `nario:nario`
  - 更新時刻: 2026-07-27 04:58（`ad-insight-fastapi.service`の起動時刻と一致）
  - 作成時刻: 2026-06-28
- **紛らわしい残骸ファイル**: `/opt/ad-insight-spec/backend/ad_insight.db`（0バイト）が
  現在も存在することを確認しました。これは[Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)が
  既に把握済みの残骸ファイルと同一です（本番運用には使われていない、`ad-insight-fastapi.service`の
  `WorkingDirectory=/opt/ad-insight-spec`が参照するのはリポジトリルート直下の`ad_insight.db`のみ）。

## 2. バックアップ運用の存在確認

**結論: 自動バックアップの仕組みは存在しません。** 以下をすべて確認しましたが、
アプリ（`ad_insight.db`）向けの自動バックアップ機構は見つかりませんでした。

| 確認箇所 | 結果 |
|---|---|
| `crontab -l`（nario） | crontab無し |
| `sudo crontab -l`（root） | crontab無し |
| `/etc/crontab` | OS標準のcron.daily/weekly/monthly起動設定のみ |
| `/etc/cron.d/*` | `certbot`（証明書更新）と`e2scrub_all`（ファイルシステムチェック）のみ。アプリ関連なし |
| `/etc/cron.daily` 等 | `apt-compat`/`dpkg`/`exim4-base`/`logrotate`/`man-db`のみ。アプリ関連なし |
| `/var/spool/cron/crontabs/` | 空 |
| `systemctl list-timers --all` | `dpkg-db-backup.timer`（dpkgパッケージDBの自動バックアップ、アプリとは無関係）はあるが、
  アプリ向けのbackup timerは無し |
| `systemctl list-unit-files \| grep backup` | 上記`dpkg-db-backup`のみ |
| `/opt/ad-insight-spec/scripts/` の中身 | `e2e_test_*.py`、`smoke_test_env.py`、`validate_sample_data.py`のみ。バックアップスクリプト無し |
| リポジトリ全体でのbackup系スクリプト検索 | 該当ファイルなし（`docs/POSTGRES_MIGRATION.md`が参照する
  バックアップ手順は、単発の`cp`コマンドを手動実行する想定の記述であり、スクリプト化されていない） |

## 3. 見つかった唯一のバックアップファイル

自動運用は無いものの、**手動で取得されたと見られる一回限りのバックアップファイルを1件だけ発見しました。**

```
/opt/ad-insight-spec/ad_insight.db.backup.20260710_075550
```

| 項目 | 値 |
|---|---|
| 作成日時 | 2026-07-10 07:55:50 UTC（**本調査時点で約31日前**） |
| サイズ | 598,016 bytes |
| 権限 | `0775` |
| 所有者 | `nario:nario` |
| 保存先 | 現行DBと**同一VM・同一ディスク**（`/opt/ad-insight-spec/`直下） |

読み取り専用で中身を確認したところ:

- テーブルは`ad_insights`のみ（`alembic_version`テーブルすら存在しない）。
  **これは、verification機能（`verification_cases`等）が本番へ導入される前の、
  かなり古い時点のスナップショットであることを意味します。**
- `ad_insights`の件数は65件（現行DBは69件。後述）。

**このバックアップは「日常運用のための定期バックアップ」ではなく、
おそらく何らかの作業（Postgres切替の試行、または他の変更）の直前に一度だけ
手動で取得されたものと推測されます**（ファイル名の命名規則が`docs/POSTGRES_MIGRATION.md`/
`docs/plans/postgresql_migration_readiness.md`記載の`cp ad_insight.db ad_insight.db.backup.$(date +%Y%m%d_%H%M%S)`と
完全に一致するため）。

## 4. 最終成功らしき証跡の確認

- `journalctl --since '30 days ago' | grep -i backup`では、`dpkg-db-backup.service`
  （OS標準、アプリと無関係）の日次実行ログのみがヒットしました。アプリのバックアップに関する
  実行ログ・成功/失敗記録は一切見つかりませんでした。
- VM上の`/opt/ad-insight-spec`のgit履歴（`git log --grep=backup`）にも、バックアップ関連の
  コミットは見つかりませんでした。
- **結論（強さ付き）: 「設定はあるが証跡がない」ではなく、「継続運用の仕組み自体が存在しない」。**
  唯一の証跡は2026-07-10の単発の手動バックアップ1件のみです。

（参考・本題とは無関係の観察）: SSHログイン試行ログに`backup`/`backuper`/`backuppc`/`rbackup`
といったユーザー名での不正ログイン試行が複数の外部IPから記録されていましたが、すべて認証前に
切断されており（`preauth`）、実際の不正アクセスの痕跡ではありません。これはインターネットに
公開されたSSHポートに対する一般的な自動スキャンであり、本調査の対象（バックアップ運用）とは
無関係です。念のため記録しますが、対応不要と考えます。

## 5. 復元可能性の判断材料

- **復元専用のスクリプト・docsはVM上・リポジトリ上ともに見つかりませんでした。**
  既存の`docs/POSTGRES_MIGRATION.md`・`docs/plans/postgresql_migration_readiness.md`には
  「バックアップファイルへコピーし直す」という単純な手順の記述はありますが、
  復元後のスモークチェック手順は[postgresql_migration_readiness.md](./postgresql_migration_readiness.md)のE章に
  あるもの（Postgres切替後を想定した内容）のみで、**SQLite単体の復元専用手順としては
  文書化されていません。**
- 設計としては「アプリを止めて、バックアップファイルを`ad_insight.db`へ上書きコピーし、
  アプリを再起動する」という単純なファイルコピー方式で足りるはずです（SQLiteはファイル
  単体でDBが完結するため）。ただし、その際に必要な所有者・権限（現状`0777`）の再設定や、
  アプリ停止の要否・停止手順が明文化された資料は見つかりませんでした。
- **復元は実施していません**（本調査は判断材料の有無を確認したのみです）。

## 6. 追加で発見した重要な事実（バックアップ運用確認の過程で判明）

本題（バックアップ運用）の調査中に、本番適用のリスク評価に直結する事実が
複数見つかりました。いずれも読み取りのみで確認し、変更は加えていません。

### 6-1. 本番のAlembic管理状態に不整合がある（重要）

`alembic_version`テーブルの値は`a1f7ccac7a04`（`asset_data`/`evaluation_data`追加の
マイグレーション）ですが、**実際のDBには次のマイグレーション`180b9b618513`
（verification機能テーブル追加）が作成するはずの`verification_cases`等のテーブルが
既に存在しています**（`verification_cases`: 0件、`verification_suggestion_evaluations`: 0件、
`verification_followups`: 0件）。

これは、`180b9b618513`が実際にはAlembic経由で適用されず、**アプリ起動時の
`Base.metadata.create_all()`によってテーブルだけが作られた**ためと考えられます
（`docs/OPERATIONS.md`に記載の「新規テーブルは起動時に自動生成されるが、既存テーブルへの
カラム追加・変更はAlembicで行う」という設計そのままの挙動です）。

**なぜこれが重要か**: 将来、本番に対して素直に`alembic upgrade head`を実行すると、
Alembicは「次は`180b9b618513`を適用する番」と認識し、`CREATE TABLE verification_cases`等を
再実行しようとして**「テーブルが既に存在する」エラーで失敗する**可能性が高いです。
これはモニターベータ（PR #91）のmigration適用の**前提条件**として、`180b9b618513`と
`d04670158813`をどう扱うか（`alembic stamp`で追いつかせる、または個別に整合性を
取り直す）を先に解決する必要があることを意味します。**この解決自体は本タスクの
スコープ外（DB更新を伴うため）とし、次タスク候補として記録するに留めます。**

### 6-2. 本番のデプロイ済みコードが`main`から大きく遅れている

VM上の`/opt/ad-insight-spec`は`git log`で`9c6da0f`（PR #79マージ）を指しており、
現在の`origin/main`（`d254aae`、PR #91まで反映済み）から**約30〜40コミット遅れています**
（`git fetch --dry-run`で`9c6da0f..d254aae`の差分を確認、実際のfetch・pullは行っていません）。
**つまりPR #91はまだ本番へデプロイされていません**（これは想定通りであり、
[monitor_beta_production_prerequisites.md](./monitor_beta_production_prerequisites.md)の
前提とも矛盾しません）。

### 6-3. psycopg2-binaryの実態は、前回整理した想定と異なっていた（訂正）

前回タスクで作成した[monitor_beta_production_prerequisites.md](./monitor_beta_production_prerequisites.md)では、
「`requirements.txt`の`psycopg2-binary==2.9.9`は本番Python 3.13.5向けホイールが無いため
経路Bでは更新が必須」と記載しましたが、**本番venvを直接確認したところ、実際には
`psycopg2-binary==2.9.12`が既にインストール済みであることが分かりました**
（`pip show psycopg2-binary`で確認。`requirements.txt`のピン値`2.9.9`とは異なる）。

- VM上の`setup.sh`（未コミットの手動セットアップスクリプト、後述）は`psycopg2-binary==2.9.9`を
  指定していますが、実際に動いているvenvには`2.9.12`が入っている、という**ドキュメント
  （setup.sh・requirements.txt）と実態の乖離**があります。おそらく、Issue #80が言及する
  「過去にPostgres切替を試みた際」に手動でアップグレードされ、そのまま残ったものと推測されます。
- **訂正**: 経路B（Postgres移行）を選ぶ場合の`psycopg2-binary`互換性リスクは、
  前回の整理より低いです。少なくとも現在の本番venvには動作しうるバージョンが
  既に入っています。ただし`requirements.txt`・`setup.sh`との不整合自体は
  [Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)の
  スコープ（運用衛生課題の整理）に該当するため、そちらで解消することを推奨します。

### 6-4. その他の未コミット・stray ファイル（VM上のみ、リポジトリには存在しない）

`/opt/ad-insight-spec`直下に、git管理外の以下のファイルが残っていました
（`git status`のUntracked filesで確認、削除・移動はしていません）:

- `setup.sh`（手動セットアップ用と見られるシェルスクリプト。`psycopg2-binary==2.9.9`固定）
- `current-freeze.txt`（`pip freeze`のスナップショットと見られるテキストファイル）
- `backend/requirements_simplified.txt`
- `=2.2.0`（ファイル名から見て、引用符無しの`pip install pkg>=2.2.0`のシェル展開ミスによる
  誤生成ファイルと推測される）

いずれも実害は無いと見られますが、[Issue #84](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/84)の
「運用衛生課題の整理」スコープに追加候補として記録します。

## リスク整理

| # | リスク | 深刻度 | 備考 |
|---|---|---|---|
| 1 | **自動バックアップが存在しない** | 高 | cron・systemd timer・スクリプトいずれも無し。今後もデータが増え続けるが、日常的な保護策が無い状態 |
| 2 | **唯一のバックアップが約31日前かつスキーマが古い** | 高 | verification機能導入前のスナップショットで、復元すると直近1ヶ月の`ad_insights`更新分・verification関連データが失われる |
| 3 | **バックアップの保存先が本番DBと同一ディスク** | 中 | ディスク障害・誤操作でVM全体に影響が及ぶ場合、バックアップも同時に失われる（オフホスト保存が無い） |
| 4 | **復元手順が文書化されていない** | 中 | 単純なファイルコピーで足りるはずだが、権限再設定・アプリ停止要否・復元後チェックが未整理 |
| 5 | **Alembic管理状態と実スキーマの不整合**（6-1） | 高 | 将来`alembic upgrade head`を素朴に実行すると失敗する可能性が高い。モニターベータ適用の直接的な前提条件 |
| 6 | **ディスク空き容量が少ない**（80%使用、残り約1.9GB） | 中 | 新規バックアップ運用を始める場合、保存先容量にも注意が必要 |
| 7 | **DBファイル権限が`0777`** | 低〜中 | 既にIssue #84で把握済み。本タスクで新規発見ではないが、バックアップ運用整備時に併せて見直す価値がある |

## 確認済み / 未確認

### 確認済み

- authoritativeなDBパス: `/opt/ad-insight-spec/ad_insight.db`
- 自動バックアップの仕組みが存在しないこと（cron/systemd timer/スクリプトいずれも無し）
- 手動バックアップが1件のみ存在すること（2026-07-10取得、同一ディスク保存）
- そのバックアップの中身（`ad_insights`のみ、65件、verification機能導入前のスキーマ）
- 本番`ad_insights`の現在の件数（69件。[Issue #83](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/83)の
  未着手チェック項目を先取りして確認）
- 本番の`alembic_version`が`a1f7ccac7a04`である一方、verification関連テーブルは
  物理的に既に存在するという不整合
- 本番デプロイ済みコードが`main`（PR #91含む）から30〜40コミット遅れていること
- 本番venvの`psycopg2-binary`実バージョンが`2.9.12`であること（`requirements.txt`のピン値`2.9.9`とは不一致）

### 未確認

- バックアップ運用を今後どう設計すべきか（頻度・世代数・保存先の方針）の意思決定
- 復元手順の正式な文書化・演習
- Alembic不整合（6-1）の具体的な解消方法の決定（`alembic stamp`の対象リビジョン等）
- ディスク容量逼迫への対応方針（不要ファイルの削除要否等、Issue #84の範囲）
