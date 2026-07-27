# PostgreSQL配置方針 比較メモ（[Issue #80](https://github.com/nario0715masa0619-create/ad-insight-spec/issues/80) 向け）

Issue #80の「PostgreSQL の配置方針を確定する（ローカルVM / 外部マネージドDB）」を
前進させるための判断材料。**今回は比較・整理・提案のみで、本番への変更は一切行っていない。**
GCPプロジェクトへの確認も、以下のコマンドによる読み取りのみ実施した:

```
gcloud sql instances list
gcloud services list --enabled --filter="name:sqladmin.googleapis.com"
gcloud compute networks list
gcloud billing projects describe ad-insight-spec
```

---

## 前提（確認済みの事実）

- 本番はGCP VM（`instance-20260626-073827`, `asia-northeast1-a`）1台構成。FastAPI/Streamlitとも
  同一VM上でsystemd管理（[前回の読み取り専用確認](postgresql_migration_readiness.md)で確認済み）
- 本番Python: 3.13.5、SQLite運用中、PostgreSQL実体は存在しない
- **Cloud SQL Admin APIは本プロジェクトで未有効化**（今回確認、有効化操作は行っていない）
- **既存のCloud SQLインスタンスは無し**（API未有効化のため確認できず＝実質的に存在しない状態）
- **デフォルトVPC（`default`、自動サブネットモード）は存在する**（今回確認）
- **billingは有効**（`billingEnabled: true`、請求先アカウント紐付け済み）（今回確認）。
  ただし実際の予算感・コスト許容度は未確認（GCPの請求先アカウント設定からは金額上限までは分からない）

---

## A. 比較メモ

| 観点 | 案A: 本番VM同居 | 案B: 外部マネージドDB（Cloud SQL for PostgreSQL） |
|---|---|---|
| 導入の容易さ | ◎ `apt install postgresql`程度。新規GCPリソース不要 | △ Cloud SQL Admin API有効化・インスタンス作成・接続方式（Public IP+許可ネットワーク or Private IP+VPC or Auth Proxy）の選定が必要 |
| 運用の単純さ（継続） | △ バックアップ・パッチ・監視を自前運用 | ◎ 自動バックアップ・自動パッチ・監視がGCP側で提供される |
| 障害時の切り分けやすさ | △ VM障害がDB/アプリ両方に波及。ただしネットワークホップが無く単純 | ○ DB障害とアプリ障害を分離できる。ただし接続経路（VPC/Auth Proxy）自体が新たな故障点になり得る |
| バックアップ/復旧のしやすさ | △ `pg_dump`等を自前でcron管理 | ◎ 自動バックアップ・Point-in-Time Recovery標準搭載 |
| セキュリティ/認証情報管理 | ○ localhost接続で完結、露出面は小さい | ○ Secret Manager等と相性が良い。ただしVPC/ファイアウォール設定を誤ると露出面が広がるリスクもある |
| コスト感 | ◎ 追加コストほぼ無し（既存VM内） | △ 最小構成でも月額コストが発生（billing自体は有効だが、実際の予算許容度は未確認） |
| 将来の保守性 | △ 手動DB管理スキルが属人化しやすい | ◎ CLAUDE.md記載の長期方針（SaaS化・認証/課金基盤）にスケールしやすい |
| 現行SQLiteからの移行しやすさ | ○ アプリ側の対応（`DATABASE_URL`動的参照）は既にPR #78で完了済みのため、AB間で有意差なし | ○ 同上 |
| 現状（GCP VM 1台構成）との相性 | ◎ 既存トポロジーそのまま | ○ 新規GCPリソース種別が増えるが、既存`default`VPCが使えるため大掛かりな変更ではない |
| 小規模運用としての現実性 | ○ 小規模ならVM同居は実際によくある構成 | ○ DB管理の手間をゼロにできる点は小規模運用（特に運用者が限られる体制）にむしろ有利 |
| 「サンプルDATABASE_URL放置」事故の抑止力 | **✕ 弱い**。`postgresql://user:password@localhost:5432/...`のような「一見完成しているが実体が無い」値を書きやすく、実際に本Issue #80の背景で一度発生している | **◎ 強い**。実在する外部ホスト名/接続名が必要になるため、プレースホルダのまま放置しにくい |

---

## B. 現時点での推奨案

**現時点の前提では、案B（外部マネージドDB = Cloud SQL for PostgreSQL）がやや有力。**
ただし断定はできない。特にコスト許容度（月額予算感）は未確認であり、そこ次第で判断が変わりうる。

## C. 推奨理由

1. CLAUDE.mdの最優先方針「本番の安定運用を維持する」に対して、バックアップ・パッチ・監視を
   GCP側に委譲できる案Bの方が、運用リスクを継続的に下げる方向に働く。
2. 今回のIssue #80自体が「`.env`がPostgreSQLを向いていたが実体が無かった」という事故を
   背景に起票されている。案Aは`localhost:5432`という「もっともらしいが実体の無い値」を
   書きやすい構成であり、**同種の事故を再発させやすい**。案Bは実在する外部ホストが必須になるため、
   この失敗モードそのものが起きにくい。
3. CLAUDE.mdの長期方針に「SaaS用の認証/課金/顧客管理」が挙がっており、将来的な拡張を見据えると
   マネージドDBの方が自然に伸ばしやすい。
4. GCPプロジェクトのbillingは既に有効であり、Cloud SQL導入の技術的な前提（API有効化・課金設定）に
   大きな障壁は無いことを確認済み。

**ただし**、以下が未確認のため、最終決定の前に埋める必要がある:
- 実際の月額コスト許容度（Cloud SQL最小構成の概算費用と比較して問題ないか）
- 運用者側にPostgreSQL/Cloud SQLの学習コストを許容する時間的余裕があるか

この2点次第では、コストと学習コストを避けて「当面は案A、将来必要になったら案Bへ再移行」という
判断も十分に合理的であり、その場合は「サンプルDATABASE_URL放置」リスクへの対策（後述）を
別途講じる前提とする。

---

## D. 推奨案（案B）を採る場合の次タスク一覧

1. **Cloud SQL Admin APIの有効化要否を判断・実施**（GCPコンソール操作、破壊的ではないが本番課金に影響するため実施前に承認を得る）
2. **インスタンス規模の試算**（最小構成 `db-f1-micro`相当からの見積もり。実際の月額コストを算出してから最終判断）
3. **接続方式の選定**（Public IP + 許可ネットワーク／Private IP経由でのVPC接続／Cloud SQL Auth Proxy のいずれか。既存`default` VPCが使えるため、Private IP接続が現実的な候補）
4. **IAM/サービスアカウント権限の確認**（Cloud SQL Client ロールの付与要否）
5. **`DATABASE_URL`の実際の接続文字列フォーマットを確定**（Issue #80のタスクへ反映）
6. 上記が固まった時点で、**[docs/plans/postgresql_migration_next_tasks.md](postgresql_migration_next_tasks.md)** のタスク6（ステージング相当のPostgres環境でのmigration成立確認）に接続する

### 追加確認候補（本番変更なし・読み取りのみで実施可能）

- `gcloud sql tiers list`（Cloud SQLの料金ティア一覧を読み取り、概算コストの根拠にする）
- `gcloud iam service-accounts list`（Cloud SQL接続に使えそうな既存サービスアカウントの有無確認）
- GCPコンソールの「お支払い」画面で、現在の月間予算アラート設定の有無を確認（コンソール閲覧のみ、変更なし）

これらは次回、必要になった時点で提案する。今回は実施していない。

---

## E. Issue #80に貼れるコメント案

```markdown
## PostgreSQL配置方針の比較検討（読み取り専用調査ベース）

「PostgreSQL の配置方針を確定する」の判断材料として、案A（本番VM同居）と案B（Cloud SQL等の
外部マネージドDB）を比較しました。詳細: docs/plans/postgresql_hosting_decision_memo.md

**現時点の前提では案B（外部マネージドDB）がやや有力**（断定はできません）。主な理由:
- 本Issueの発端になった「.envがPostgreSQLを向いていたが実体が無かった」という事故は、
  案Aの構成（`localhost:5432`という一見完成した値を書きやすい）だと再発しやすい一方、
  案Bは実在する外部ホストが必須になるため同種の事故が起きにくい
- バックアップ・パッチ・監視をGCP側に委譲でき、CLAUDE.mdの最優先方針
  「本番の安定運用を維持する」と整合する

読み取り専用で確認した事実:
- 本プロジェクトはCloud SQL Admin API未有効化・既存Cloud SQLインスタンス無し
- デフォルトVPCは既に存在（`default`, auto subnet mode）
- billingは有効化済み

**未確認のため、最終決定の前に埋める必要がある点**:
- Cloud SQL最小構成の実際の月額コスト許容度
- 運用側のPostgreSQL/Cloud SQL学習コストの許容度

これらが埋まり次第、次タスク（API有効化要否判断・インスタンス規模試算・接続方式選定）に進めます。
本番への変更は今回行っていません。
```

---

## 結論

- **現時点の前提では案B（外部マネージドDB）が有力候補**だが、コスト許容度・運用体制という
  2つの未確認事項が残っているため、Issue #80のチェックリストの当該項目はまだ「決定」にはできない。
- 本番VM・`.env`・migrationには一切触れていない。読み取り専用のGCP確認のみ実施。

## 次の一手

Issue #80の「PostgreSQL の配置方針を確定する」チェックリスト項目を、
**「案Bを軸に検討中。コスト試算待ち」**という中間状態に更新することを提案する
（未決定のまま放置せず、かつ断定もしない状態として）。次のアクションは
「Cloud SQL最小構成の概算コストを確認する」こと（読み取りのみ、`gcloud sql tiers list`等で対応可能）。
