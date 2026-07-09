# Asset/Evaluation Split — Phase 2: Read Adapter / Upcaster 設計

**対象フェーズ**: Phase 2（read adapter設計・実装）＋ Phase 1（DBカラム追加・v0スキーマ導入、2026-07-09に公式化）
**前提（2026-07-09 更新）**: Antigravity側のローカルPoC（`feature/asset-evaluation-split-phase1`、未push）はレビュー参考のみに使い、リポジトリには一切輸入しなかった。代わりに、本ドキュメントで洗い出したPoCの既知問題（`alembic.ini`の相対パス問題・`asset_meta`名称衝突・datetime JSON化の落とし穴）を踏まえて**このリポジトリ上でPhase 1を独自に設計・実装**した。現行 main の `AdInsight` モデルには `asset_data`/`evaluation_data` カラムが実在する（ブランチ`feature/asset-evaluation-phase1-columns-schemas`、下記参照）。
**ステータス**: 🟢 Phase 1（カラム＋v0スキーマ）実装済み・ローカル検証済み ／ Phase 2第一段階（adapter scaffold）実装済み（PR #61）／ downcast変換ロジック本体は未実装
**実装状況**:
- Phase 1: `backend/alembic/`（baseline + カラム追加の2マイグレーション）、`AdInsight.asset_data`/`evaluation_data`カラム、`backend/app/schemas/asset_v0.py`・`evaluation_v0.py`を実装済み。**本番DBへのマイグレーション適用はまだ実施していない**（別途確認のうえ実施）。
- Phase 2: `backend/app/services/asset_evaluation_adapter.py::resolve_spec_data`実装済み（PR #61）。`specs.py::get_spec`/`list_specs`への配線も実施済み（本ドキュメントの「specs.py 配線方針」で決めたとおり、カラム追加と同じPRで実施）。ただし`asset_data`/`evaluation_data`は常にNULL（dual-write未実装のため）で、実際のdowncast変換ロジックはまだ書かれていない（fail-softでspec_dataへフォールバックする）。本番のAPIレスポンス形状への影響は無い。

---

## 📋 背景・目的

現在`AdInsight`は`spec_data`（JSON正本、`ad_insight_spec v0.2`全体）1カラムに全データを持つ設計。Phase 1でこれを将来的に「観測事実（asset_data）」と「評価・解釈（evaluation_data）」に分割する準備として、2つのnullableカラムを追加した。

Phase 2の目的は、**dual-write（両カラムへの実書き込み）を始める前に、読み出し側の抽象化（adapter）を先に固める**こと。これにより:
- dual-writeが始まった後も、既存UI（`streamlit_app.py`）・既存API（`GET /specs/{asset_id}`等）が一切変更を必要としない
- 新旧データ形状（`spec_data`のみの行 / `asset_data`+`evaluation_data`が入った行）が混在する移行期間を安全に扱える
- Phase 3（dual-write実装）が始まる前に、変換ロジックのテストとレビューを完了できる

当初「このPhaseではコードは書かず設計のみ」としていたが、2026-07-09にPhase 1（カラム＋v0スキーマ）・Phase 2 adapter scaffoldとも実装まで完了した（下記「実装状況」参照）。downcast本体の実装のみ残っている。

---

## 🎯 Read Adapter の責務

### 1つの入口関数として設計する（実装済みシグネチャ）

本ドキュメント初版では `resolve_spec_data(record: AdInsight) -> dict` というORMレコード直渡しの
シグネチャを提案していたが、実装時（PR #61）に **dict直渡し**へ変更した:

```python
def resolve_spec_data(
    spec_data: Dict[str, Any],
    asset_data: Optional[Dict[str, Any]] = None,
    evaluation_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

変更理由:
- `record: AdInsight`を受け取る設計だと、adapter単体のユニットテスト（本ドキュメントの実装タスク3「両方に値がある合成テストデータで変換できることを確認する」）を書くために毎回SQLAlchemyの`AdInsight`インスタンス（またはモック）を組み立てる必要があり、adapterがDB層に不必要に結合する。
- dict直渡しなら、`specs.py`側は`resolve_spec_data(record.spec_data, record.asset_data, record.evaluation_data)`のように呼ぶだけで済み、adapter自体はSQLAlchemyに一切依存しない純粋関数のまま保てる。
- `asset_data`/`evaluation_data`カラムが現行mainに存在しない今の状態でも、adapterを「将来存在するはずの引数」を明示的なオプショナル引数として持つ形で実装・テストできる（`record`渡しだと、存在しない属性へのアクセスをどう扱うかという余計な分岐が発生する）。

判定ロジック（feature flagは不要、引数の状態がそのまま切替条件になる。実装済み）:

| `asset_data` | `evaluation_data` | 挙動 | 実装状況 |
|---|---|---|---|
| None | None | `spec_data`をそのまま返す（現状の全レコードがこれ。無変更） | ✅ 実装済み |
| 値あり | 値あり | `asset_data`+`evaluation_data`から`spec_data`互換dictを **再構築** して返す（downcast） | ❌ 未実装（下記オープン課題1〜3が未解決のため） |
| 値あり | None（またはその逆） | 不整合データとみなし、`spec_data`側にフォールバック（fail-soft。ログに警告を出す） | 🟡 暫定実装済み（本来の「不整合」判定ではなく、「downcast未実装につき常にfail-softする」という広い意味で暫定運用。実際にasset_data/evaluation_dataが導入された時点で、この分岐を「downcast実行」と「真の不整合時のfail-soft」に分離する） |

この「引数の状態がそのまま分岐条件」という設計は、本セッションで実装済みの`video_cuts`の新旧形状判定（`diagnostics.video_cuts`に`generation_status`キーがあるか否かで新旧を判定する、`frontend/streamlit_app.py::render_asset_detail`）と同じパターンであり、このリポジトリで既に実績のある方式。新規のfeature flag機構は導入しない。

### downcast（`asset_data + evaluation_data → legacy spec_data`）の変換方針（2026-07-09、Phase 1実装により確定）

| legacy `spec_data`のキー | 変換元 | 備考 |
|---|---|---|
| `asset_meta` | `asset_data.asset_meta`（`AssetMetaV0`、`backend/app/schemas/asset_v0.py`） | ✅ 解決済み（オープン課題1）。`AssetMetaV0`は`platform`/`campaign_name`/`adset_name`/`ad_name`/`analysis_period`/`external_ids`を含むlegacy `AssetMeta`のスーパーセットとして実装したため、null埋め不要でそのまま転記できる |
| `creative_core.format` | `asset_data.media_info.media_type` | ✅ 解決済み。マッピング表を作らず、`MediaInfoV0.media_type`の型自体を既存`FormatEnum`（`app.schemas.ad_insight`）に統一したため変換不要 |
| `creative_core.duration_seconds` | `asset_data.media_info.duration_seconds` | そのまま |
| `diagnostics` | `evaluation_data.diagnostics` | `EvaluationJsonV0.diagnostics`は既存`Diagnostics`型をそのまま再利用しているため、実質そのまま転記可能 |
| `diagnostics.video_cuts.video_cuts[].start_seconds/end_seconds` | `asset_data.asset_structure.cuts[]`（`CutSpan`、`cut_id`で結合） | ✅ 解決済み（オープン課題2）。`CutSpan`（`asset_v0.py`）を唯一の時間情報の正本とし、`EvaluationJsonV0.diagnostics`側の`VideoCutContent.start_seconds/end_seconds`は定義しない（既存どおりOptional）。downcast実装時に`cut_id`で突き合わせて補完する |
| `performance` | `evaluation_data.performance` | そのまま |
| `landing_page` | `evaluation_data.landing_page_analysis` | そのまま |
| `_metadata` | `asset_data.asset_meta`（`created_at`/`analysis_version`/`source_type`）+ `evaluation_data.evaluation_meta`（`evaluator_model`/`processing_time_ms`/`validation_status`/`validation_notes`/`analysis_tools_used`） | ✅ 解決済み（オープン課題3）。legacy `Metadata`の9フィールドを「取り込み時」と「評価実行時」に分割済み（`evaluation_v0.py`のdocstring参照）。`json_schema_version`の具体的な復元方法のみ、downcast実装時の判断として残す |

### 旧データ・新データの read path

- 旧データ（`spec_data`のみ、全既存レコードがこれに該当）: **無変換でそのまま返す**。Phase 2実装後も既存の`get_spec`/`list_specs`の挙動は1バイトも変わらない。
- 新データ（Phase 3でdual-write開始後に作られるレコード）: adapterがdowncastして`spec_data`互換形状に変換してから返す。**フロントエンド・既存APIレスポンス形状は変更しない。**
- 将来的に`asset_data`/`evaluation_data`を直接返す新APIエンドポイント（例: `GET /specs/{asset_id}/asset`）が必要になった場合は、Phase 2の範囲外として別途設計する（既存UIは`spec_data`互換形状のみを消費し続ける前提のため、当面は不要）。

### JSON化に関する実装上の注意（Phase 1レビューで判明した既知の落とし穴）

`AssetJsonV0`/`EvaluationJsonV0`は`datetime`型フィールドを持つため、Pydantic v1で`.dict()`を直接使うと`TypeError: Object of type datetime is not JSON serializable`で失敗する（本セッション中に実際に発生・修正した既知のバグと同一パターン）。adapter・将来のdual-write実装のいずれも、`json.loads(model.json())`を経由すること。

---

## 🏗 どの層に置くか

**`backend/app/services/` 配下に新規モジュールとして置く**（`asset_evaluation_adapter.py`）。

理由:
- `backend/app/repositories/ad_insight_repository.py`は現状DBクエリのみを担うシンプルな層（`get_latest_by_asset_id`等）で、ビジネスロジック（形状変換）を持たない設計が一貫している。ここに変換ロジックを混ぜると責務が曖昧になる。
- `backend/app/services/converter_service.py`は「分析結果 → `spec_data`を**新規構築**する」役割（書き込み時）であり、「DBから読み出した既存レコードを整形する」役割（読み出し時）とは方向が逆。読み出し変換は別モジュールにする。
- `backend/app/api/routes/specs.py`には、既存の`_build_decision_support_diff`のように「DBの生データを返す前に加工するヘルパー」を直接置くパターンが既にあるが、`resolve_spec_data`は再利用性が高く、`get_spec`/`list_specs`の両方から呼ばれるため、routesファイルに直書きせず`services/`に切り出す。

呼び出し箇所: `specs.py`の`get_spec`/`list_specs`内、`record.spec_data`を直接使っていた箇所を`resolve_spec_data(record.spec_data, record.asset_data, record.evaluation_data)`に置き換え済み（詳細は下記「specs.py 配線方針」）。

---

## 🚩 feature flag / 切替条件

不要。上記のとおり、引数（将来的にはレコードの`asset_data`/`evaluation_data`カラム）がnullかどうかがそのまま切替条件になる。環境変数やDB設定によるON/OFFフラグは導入しない（切替のための追加の状態を持たない方が、移行期間中の挙動予測がしやすい）。

---

## 🔌 specs.py 配線方針（2026-07-09: 設計どおり実装済み）

### 呼び出し箇所の具体的な置き換え案

`backend/app/api/routes/specs.py`には`record.spec_data`を直接展開している箇所が2つある:

- `list_specs`（L330）: `{**rec.spec_data, "version": rec.version, "created_at": rec.created_at.isoformat()}`
- `get_spec`（L389, L395）: `{**record.spec_data, "version": record.version, "created_at": record.created_at.isoformat()}` に加え、`decision_support_diff`計算のために`record.spec_data.get("diagnostics", {})`も参照している

実際に適用した変更（`backend/app/api/routes/specs.py`）:

```python
# list_specs 内
resolved = resolve_spec_data(rec.spec_data, rec.asset_data, rec.evaluation_data)
{**resolved, "version": rec.version, "created_at": rec.created_at.isoformat()}

# get_spec 内
resolved_spec_data = resolve_spec_data(record.spec_data, record.asset_data, record.evaluation_data)
result = {**resolved_spec_data, "version": record.version, "created_at": record.created_at.isoformat()}
...
diagnostics = resolved_spec_data.get("diagnostics", {}) or {}
```

置き換えは2ファイル3行程度で完了。`asset_data`/`evaluation_data`カラムはまだ常にNULLのため、`resolve_spec_data`は無条件で`spec_data`を無変換で返し、既存レスポンス形状は1バイトも変わらない。

### 組み込みタイミングの判断（実装タスク5「組み込み判断」への回答、2026-07-09に実行）

当初の判断どおり、**`asset_data`/`evaluation_data`カラムを追加するPRと同じPRで配線した**（このリポジトリでPhase 1を実装したPR）。カラムが実在するようになった時点で配線しても、実際にはNULLしか入っていないため無変換パスしか通らず、リスクはゼロだった。

### オープン課題1〜3への対応

オープン課題1〜3（asset_meta名称衝突・カット情報の一次情報源・_metadata再構成方針）は、v0スキーマ（`asset_v0.py`/`evaluation_v0.py`）の設計時にすべて解決済み（詳細は上記の変換方針テーブルおよび下記「オープン課題」セクション参照）。ただし、これは「スキーマの形が変換可能な形になった」という意味であり、**実際にdictを変換するdowncastコード自体はまだ書かれていない**（resolve_spec_dataは引き続きfail-softで無変換）。downcast本体の実装は次のタスクとして残る。

---

## ⚠️ オープン課題（2026-07-09: すべてスキーマ設計レベルでは解決済み）

1. **`asset_meta`の名称衝突** — ✅ 解決済み。`AssetMetaV0`（`asset_v0.py`）はlegacy `AssetMeta`（`app/schemas/ad_insight.py`）の全フィールドを含むスーパーセットとして実装した。呼称は「legacy asset_meta」（spec_data側）／「v0 asset_meta」（asset_data側）で区別する。
2. **カット情報の一次情報源** — ✅ 解決済み。`asset_data.asset_structure.cuts`（`CutSpan`）を一次情報源とし、`evaluation_data.diagnostics.video_cuts`側は既存`VideoCutContent`をそのまま再利用（`start_seconds`/`end_seconds`はOptionalのまま、独自定義しない）。
3. **`_metadata`相当情報の再構成方針** — ✅ 解決済み。legacy `Metadata`の9フィールドを「取り込み時」（`AssetMetaV0`）と「評価実行時」（`EvaluationMetaV0`）に分割した。`json_schema_version`の具体的な復元式のみ、downcast実装時に決定する残課題として残る。

**残っている作業**: 上記はスキーマの「形」が変換可能になっただけで、`asset_data`+`evaluation_data`の実際のdictを`spec_data`互換dictへ変換するPythonコード（downcast本体）はまだ実装していない。これは次のタスク。

---

## ✅ 実装タスク（issue粒度）

1. **[設計]** 上記オープン課題1〜3を解決し、`spec_data`⇄(`asset_data`, `evaluation_data`)の完全なフィールド対応表を確定する — ✅ 完了（2026-07-09、`asset_v0.py`/`evaluation_v0.py`実装と同時）
2. **[実装]** `resolve_spec_data(spec_data, asset_data=None, evaluation_data=None) -> dict`を実装 — ✅ 完了（PR #61）。旧データ（spec_dataのみ）の無変換パスのみ実装。**新データ変換パス（downcast本体）は未実装**（スキーマは確定したが、変換コード自体はまだ書かれていない）
3. **[テスト]** `resolve_spec_data`の単体テスト — 🟡 一部完了（PR #61）。「両方None→無変換」「片方/両方非None→fail-softフォールバック＋警告ログ」は実装・テスト済み。「合成テストデータでの実際のdowncast変換」はdowncast本体が未実装のため未着手
4. **[テスト]** `streamlit_app.py`のレンダリング関数が`resolve_spec_data`の新データ変換パス出力に対しても壊れずに表示できることの確認 — ⏳ 未着手（downcast本体が未実装のため対象がない）
5. **[組み込み判断]** `specs.py::get_spec`/`list_specs`への`resolve_spec_data`組み込み — ✅ 完了（2026-07-09、カラム追加と同じPRで実施）
6. **[ドキュメント]** 本ファイルの対応表を確定版として更新し、`docs/specs/`配下に正式スキーマドキュメントを作成 — 🟡 本ファイルの対応表は確定済み。`docs/specs/`配下への独立ドキュメント化はまだ未着手
7. **[Phase 1: カラム追加]** `AdInsight.asset_data`/`evaluation_data`カラム追加、Alembic導入 — ✅ 完了（2026-07-09）。`backend/alembic/`にbaseline+カラム追加の2マイグレーション、`backend/app/models/ad_insight.py`にカラム追加。**本番DBへの適用は未実施**（別途確認のうえ実施）
8. **[Phase 1: v0スキーマ]** `AssetJsonV0`/`EvaluationJsonV0`等の実装 — ✅ 完了（2026-07-09）。`backend/app/schemas/asset_v0.py`・`evaluation_v0.py`
9. **[次のタスク]** downcast本体（`asset_data + evaluation_data → spec_data`の実際の変換コード）の実装 — ⏳ 未着手。dual-write（Phase 3）が始まり、実際に`asset_data`/`evaluation_data`が入ったレコードが出てくる前後で着手する想定

---

## 🔗 関連ドキュメント

- `docs/specs/ad_insight_json_schema_v0_2.md` — 現行`spec_data`のトップレベル構造
- `docs/specs/video_cuts_json_schema_v1_0.md` — 新旧形状判定パターンの先行事例（`generation_status`キーの有無による判定）
- `backend/app/services/asset_evaluation_adapter.py` — Phase 2実装済みの`resolve_spec_data`（spec_dataのみパススルー、PR #61）
- `backend/tests/test_asset_evaluation_adapter.py` — 上記の単体テスト
- `backend/app/schemas/asset_v0.py` / `evaluation_v0.py` — Phase 1実装済みのv0スキーマ
- `backend/alembic/` — Phase 1実装済みのマイグレーション一式
- `docs/DEPLOYMENT.md`（「1a. DBマイグレーション」） — Alembicの運用手順

最終更新: 2026-07-09
ステータス: Phase 1（カラム＋v0スキーマ）実装・ローカル検証済み、本番適用は未実施 ／ Phase 2 adapter scaffold・specs.py配線 実装済み ／ downcast本体は未着手
