# Asset/Evaluation Split — Phase 2: Read Adapter / Upcaster 設計

**対象フェーズ**: Phase 2（read adapter設計・実装）＋ Phase 1（DBカラム追加・v0スキーマ導入、2026-07-09に公式化）
**前提（2026-07-09 更新）**: Antigravity側のローカルPoC（`feature/asset-evaluation-split-phase1`、未push）はレビュー参考のみに使い、リポジトリには一切輸入しなかった。代わりに、本ドキュメントで洗い出したPoCの既知問題（`alembic.ini`の相対パス問題・`asset_meta`名称衝突・datetime JSON化の落とし穴）を踏まえて**このリポジトリ上でPhase 1を独自に設計・実装**した。現行 main の `AdInsight` モデルには `asset_data`/`evaluation_data` カラムが実在する（ブランチ`feature/asset-evaluation-phase1-columns-schemas`、下記参照）。
**ステータス**: 🟢 Phase 1（カラム＋v0スキーマ）実装済み・ローカル検証済み ／ Phase 2第一段階（adapter scaffold）実装済み（PR #61）／ downcast第一バッチ（`_downcast_asset_meta`のみ、未配線）実装済み（PR #65、マージ待ち）／ オープン課題4・5は詳細調査＋6項目の保存方針比較・推奨案まで整理済み（PR #66、docs-only） ／ フィールド追加・downcast本体・`resolve_spec_data`への配線は引き続き未実装
**実装状況**:
- Phase 1: `backend/alembic/`（baseline + カラム追加の2マイグレーション）、`AdInsight.asset_data`/`evaluation_data`カラム、`backend/app/schemas/asset_v0.py`・`evaluation_v0.py`を実装済み。**本番DBへのマイグレーション適用はまだ実施していない**（別途確認のうえ実施）。
- Phase 2 adapter scaffold: `backend/app/services/asset_evaluation_adapter.py::resolve_spec_data`実装済み（PR #61）。`specs.py::get_spec`/`list_specs`への配線も実施済み（本ドキュメントの「specs.py 配線方針」で決めたとおり、カラム追加と同じPRで実施）。ただし`asset_data`/`evaluation_data`は常にNULL（dual-write未実装のため）で、`resolve_spec_data`の公開挙動は無変換パススルーのまま。
- Phase 2 downcast第一バッチ（2026-07-09、PR #65）: `_downcast_asset_meta()`を実装（`asset_meta`のみを対象にした独立部品、単体テスト済み）。**`resolve_spec_data`にはまだ配線していない**。既存API・CLIの挙動には一切影響なし。
- オープン課題4・5 詳細調査（2026-07-09、docs-only、PR #66）: `input_metadata`/`creative_core`の各フィールドを実コード調査し「埋められる／新規保存が必要／埋められない」に分類。真のブロッカーは6項目（`mode`/`file_paths`/`visuals`/`tone`/`ai_labels`/`ocr_extracted_text`）と特定。
- 6項目の保存方針比較（2026-07-09、docs-only）: 上記6項目それぞれについて保存先候補（`AssetMetaV0`拡張／別ブロック追加／`CreativeCoreSchema`部分再利用）をbackward compatibility・実装コスト・将来の検索性で比較し、推奨案を1つずつ確定（下記「🗂 6項目の保存方針比較」参照）。**コード変更なし**。フィールド追加自体はまだ未実施（ユーザー確認待ち）。

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
| `input_metadata` | （変換元なし） | ❌ **未解決（オープン課題4、2026-07-09発見）**。`AssetJsonV0`/`EvaluationJsonV0`のどちらにも`mode`/`source_type`/`input_timestamp`/`file_paths`/`api_source`に対応するフィールドが無い。`AdInsightSpec.input_metadata`は必須フィールドのため、これが埋まらない限り完全なdowncastは不可能 |
| `asset_meta` | `asset_data.asset_meta`（`AssetMetaV0`、`backend/app/schemas/asset_v0.py`） | ✅ 解決済み（オープン課題1）。`AssetMetaV0`は`platform`/`campaign_name`/`adset_name`/`ad_name`/`analysis_period`/`external_ids`を含むlegacy `AssetMeta`のスーパーセットとして実装したため、null埋め不要でそのまま転記できる。**2026-07-09: `_downcast_asset_meta()`として実装済み（`asset_evaluation_adapter.py`、単体テスト済み、`resolve_spec_data`へは未配線）** |
| `creative_core.format` | `asset_data.media_info.media_type` | ✅ 解決済み。マッピング表を作らず、`MediaInfoV0.media_type`の型自体を既存`FormatEnum`（`app.schemas.ad_insight`）に統一したため変換不要 |
| `creative_core.duration_seconds` | `asset_data.media_info.duration_seconds` | そのまま |
| `creative_core`のその他フィールド（`primary_text`/`headline`/`body_text`/`call_to_action`/`visuals`/`tone`/`ai_labels`/`platform_specific`/`ocr_extracted_text`/`llm_model`/`llm_success`/`llm_retry_count`/`llm_error`） | （変換元なし） | ❌ **未解決（オープン課題5、2026-07-09発見）**。`AssetJsonV0`/`EvaluationJsonV0`は`format`と`duration_seconds`以外の`CreativeCore`フィールドに対応する変換元を持たない。`creative_core.format`は必須フィールドのため型自体は埋まるが、これらの自由文・分析系フィールドは埋められない |
| `diagnostics` | `evaluation_data.diagnostics` | `EvaluationJsonV0.diagnostics`は既存`Diagnostics`型をそのまま再利用しているため、実質そのまま転記可能 |
| `diagnostics.video_cuts.video_cuts[].start_seconds/end_seconds` | `asset_data.asset_structure.cuts[]`（`CutSpan`、`cut_id`で結合） | ✅ 解決済み（オープン課題2、方針のみ）。`CutSpan`（`asset_v0.py`）を唯一の時間情報の正本とし、`EvaluationJsonV0.diagnostics`側の`VideoCutContent.start_seconds/end_seconds`は定義しない（既存どおりOptional）。downcast実装時に`cut_id`で突き合わせて補完する。**変換コード自体は未実装（Phase 2 downcast第一バッチのスコープ外）** |
| `performance` | `evaluation_data.performance` | そのまま |
| `landing_page` | `evaluation_data.landing_page_analysis` | そのまま |
| `views` | （変換元なし） | `AdInsightSpec.views`はOptionalのため、downcast時は省略（None）でよい。追加対応不要 |
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
4. **`input_metadata`の変換元が存在しない（2026-07-09発見、2026-07-09詳細調査済み）** — ❌ 未解決（設計未確定）。詳細は下記「オープン課題4・5 詳細調査」参照。
5. **`creative_core`の自由文・分析系フィールドの変換元が存在しない（2026-07-09発見、2026-07-09詳細調査済み）** — ❌ 未解決（設計未確定）。詳細は下記「オープン課題4・5 詳細調査」参照。

**残っている作業**: オープン課題1〜3の解決（スキーマの「形」の確定）と、`_downcast_asset_meta()`（`asset_meta`のみ対象）の実装・単体テストまでは完了した（PR #65）。オープン課題4・5が未解決のため、**完全な**downcast（`spec_data`と同等の完全な形を再構築するコード）は実装できない。これは次のバッチのタスク。

---

## 🔍 オープン課題4・5 詳細調査（2026-07-09、実コード調査ベース）

推測ではなく、実際のデータフロー（`converter_service.py`・`analysis_orchestrator.py`・`llm_response.py`）を
読んで、各フィールドについて「現行パイプラインに実データが存在するか」「v0スキーマの既存フィールドで
代替できるか」を確認した。**コード変更は行っていない（docs-onlyの調査）**。

### 調査で分かった重要な事実

`creative_core`の`primary_text`/`headline`/`body_text`/`call_to_action`/`platform_specific`は、
**現行の legacy spec_data 生成パイプラインでも常に`None`**（`converter_service.py::_populate_creative_core`
L171-178、`"primary_text": None,  # Would come from OCR in full implementation`という未実装コメント付き）。
つまりこれらは「downcastで埋められない」のではなく「現行システムにそもそも実データが存在しない」項目であり、
downcast後も`None`のままにしておけば**現行の実挙動と完全に一致する**（新たな情報欠落にはならない）。

同様に`creative_core.llm_model`/`llm_success`/`llm_retry_count`/`llm_error`も、legacy spec_dataでは
`creative_core`側に書き込まれず常に`None`（実際の値は`diagnostics.llm_model`等にのみ書き込まれる、
`converter_service.py::_populate_diagnostics` L277-280）。この値は`EvaluationJsonV0.diagnostics`
（`Diagnostics`型再利用、オープン課題3で解決済み）に既に含まれているため、追加対応は不要。

これにより、**本当に「新規データ保存」が必要な項目は当初の想定より少ない**ことが分かった
（詳細は下表）。

### input_metadata フィールド別調査

| フィールド | 現行パイプラインでの実データ | 発生箇所 | v0スキーマでの対応 | 分類 |
|---|---|---|---|---|
| `mode` | あり（`/analyze`のリクエストパラメータ、毎回動的） | `converter_service.py::_populate_input_metadata`引数 | 対応フィールド無し | **新規保存が必要** |
| `source_type` | あり（ただし現状は常に固定値`"local_file"`） | `_populate_input_metadata` L132（ハードコード） | `AssetMetaV0.source_type`が同じ意味・同じ値を持つ既存フィールド | **埋められる**（既存v0フィールドで代替可） |
| `input_timestamp` | あり（`datetime.now()`、analyze実行時刻） | `_populate_input_metadata` L133 | `AssetMetaV0.created_at`が意味的に同じ役割の既存フィールド | **埋められる**（既存v0フィールドで代替可） |
| `file_paths`（`creative_video`/`creative_images`/`landing_page_html`の構造化オブジェクト） | あり（アップロードファイルパス、毎回動的） | `_populate_input_metadata` L134-138 | `AssetMetaV0.source_ref`は単一文字列のみで、構造化された複数パスを表現できない | **新規保存が必要**（既存`source_ref`では形状が合わない） |
| `api_source` | 常に`None`（Meta/Google/TikTok API連携は未実装） | `_populate_input_metadata` L139（固定`None`） | 対応フィールド無し | **埋められない**（現行システムにも実データ自体が存在しない。Noneのままで現行挙動と一致） |

### creative_core フィールド別調査

| フィールド | 現行パイプラインでの実データ | 発生箇所 | v0スキーマでの対応 | 分類 |
|---|---|---|---|---|
| `format` | あり | ✅解決済み | `MediaInfoV0.media_type` | 解決済み |
| `duration_seconds` | あり | ✅解決済み | `MediaInfoV0.duration_seconds` | 解決済み |
| `primary_text`/`headline`/`body_text`/`call_to_action` | **常に`None`**（未実装） | `converter_service.py::_populate_creative_core` L171-174 | 対応フィールド無し | **埋められない**（現行システムにも実データ自体が存在しない。Noneのままで現行挙動と一致） |
| `visuals`（dominant_colors/composition/style/clarity） | あり（実LLM出力、`VisualsSchema`） | `analysis_orchestrator.py` L526 → `llm_response.py::CreativeCoreSchema.visuals` | 対応フィールド無し | **新規保存が必要** |
| `tone`（primary_tone/emotional_appeal/call_to_action） | あり（実LLM出力、`ToneSchema`） | `analysis_orchestrator.py` L527 | 対応フィールド無し | **新規保存が必要** |
| `ai_labels` | あり（実LLM出力、`List[str]`） | `analysis_orchestrator.py` L528 | 対応フィールド無し | **新規保存が必要** |
| `platform_specific` | 常に`None`（未実装） | `_populate_creative_core` L178 | 対応フィールド無し | **埋められない**（現行システムにも実データ自体が存在しない） |
| `ocr_extracted_text` | 実データは計算されているが、**現行`_populate_creative_core`はこの値を全く読んでおらず、legacy spec_data側も常にデフォルト値`""`のまま**（既存の未使用ロジック、本調査では変更しない） | `analysis_orchestrator.py` L321/326/529（`ocr_text`変数） | `AssetStructureV0.ocr_segments[].text`が近い情報を持つが、粒度が異なる（単一の全体OCR文字列 vs カット単位の複数セグメント）ため完全な一致は保証されない | **新規保存が必要**（`ocr_segments`で部分的に近似可能だが別途検討要） |
| `llm_model`/`llm_success`/`llm_retry_count`/`llm_error`（creative_core側） | 実データはあるが、**legacy spec_data.creative_core側には元々一切書き込まれず常に`None`**（実際の値は`diagnostics`側にのみ反映） | `converter_service.py::_populate_diagnostics` L277-280 | `EvaluationJsonV0.diagnostics`（オープン課題3で解決済み）が既にこの値を持つ | **対応不要**（diagnostics経由で解決済み。creative_core側は現行スペックでも常に`None`のため合わせる必要なし） |

### 3分類まとめ

**① 埋められる項目（既存v0スキーマのままdowncastロジックだけで導出可能。schema変更不要）**
- `input_metadata.source_type` ← `asset_data.asset_meta.source_type`
- `input_metadata.input_timestamp` ← `asset_data.asset_meta.created_at`

**② 新規保存が必要な項目（実データは現行パイプラインに存在するが、v0スキーマへのフィールド追加が必要）**
- `input_metadata.mode`
- `input_metadata.file_paths`
- `creative_core.visuals`
- `creative_core.tone`
- `creative_core.ai_labels`
- `creative_core.ocr_extracted_text`（部分的近似のみ、要別途検討）

**③ 埋められない項目（現行システムにも実データ自体が存在しない。downcast後もNoneで現行挙動と一致するため、実害のあるブロッカーではない）**
- `input_metadata.api_source`
- `creative_core.primary_text` / `headline` / `body_text` / `call_to_action` / `platform_specific`

**④ 対応不要（既に別のオープン課題で解決済み）**
- `creative_core.llm_model` / `llm_success` / `llm_retry_count` / `llm_error`（`diagnostics`経由、オープン課題3）

### 推奨方向性（2026-07-09時点の暫定メモ、下記「6項目の保存方針比較」で正式化）

上記③は実害のないNoneであり、downcastの完全性を妨げる真のブロッカーは②の6項目のみと分かった。
これにより、当初懸念していたよりも小さいスキーマ変更で完全なdowncastに近づける見込みが立った。
6項目それぞれの保存先の正式な比較・推奨案は、下記「🗂 6項目の保存方針比較」セクションを参照
（本セクションの暫定メモは、そちらでの検討結果に統合済み）。

---

## 🗂 6項目の保存方針比較（2026-07-09、docs-only設計バッチ）

オープン課題4・5の詳細調査（上記）で特定した真のブロッカー6項目について、保存先の選択肢を
比較し、推奨案を1つに絞った。**コード変更は行っていない（docs-onlyの設計比較）**。

### 比較する保存先パターン

- **パターンA: `AssetMetaV0`拡張** — `asset_data.asset_meta`（`asset_v0.py`）に新規フィールドを直接追加する
- **パターンB: `asset_data`/`evaluation_data`の別ブロックに新規フィールド追加** — `AssetMetaV0`以外の
  既存/新規ブロック（`AssetStructureV0`・`EvaluationJsonV0`直下など）に追加する
- **パターンC: `llm_response.CreativeCoreSchema`の部分再利用** — 既存のLLM出力そのものの型を
  `evaluation_data`側でそのまま再利用する（`visuals`/`tone`/`ai_labels`にのみ適用可能）

### 項目別比較

#### 1. `input_metadata.mode`

| 観点 | 内容 |
|---|---|
| source | `POST /analyze`のリクエストパラメータ（`converter_service.py::_populate_input_metadata`引数、`InputModeEnum`の4値のいずれか） |
| パターンA | `mode: InputModeEnum`を`AssetMetaV0`に追加。既存の`source_type`/`created_at`と同じ「取り込み時点の情報」という性質に合致 |
| パターンB | 該当なし（Aと実質同じ置き場所以外に自然な候補がない） |
| パターンC | 該当なし |
| backward compatibility | legacy `spec_data.input_metadata.mode`は必須フィールド。埋まらないと`AdInsightSpec`としての完全性が失われる（ただし`specs.py`は現状Pydantic再検証していないため、実害は「値が欠落したdictが返る」程度に留まる） |
| 実装コスト | 低。既存`InputModeEnum`（`app.schemas.ad_insight`）を再利用するだけで新規enum定義は不要 |
| 将来の検索性 | 低優先度。`mode`はフィルタ用途がほぼ無く、`format`のように一覧APIで絞り込みに使われる想定も薄い |
| **推奨** | **パターンA（`AssetMetaV0.mode`）** |

#### 2. `input_metadata.file_paths`

| 観点 | 内容 |
|---|---|
| source | アップロードされたファイルパス（`converter_service.py::_populate_input_metadata` L134-138、`creative_video`/`creative_images`/`landing_page_html`の構造化オブジェクト） |
| パターンA | `file_paths: FilePaths`（既存`FilePaths`型を再利用）を`AssetMetaV0`に追加。ただし既存`source_ref`（単一文字列、「元ファイルパスや外部APIレスポンスIDなど、取り込み元への参照」）と役割が重複する懸念あり |
| パターンB | `AssetStructureV0`への追加も考えられるが、同モデルは「カット・文字起こし・OCR」という時系列構造データ向けの入れ物であり、ファイルパスの性質とは合わない |
| パターンC | 該当なし |
| backward compatibility | legacy側は必須ではない（`Optional[FilePaths]`）ため、欠落しても`AdInsightSpec`のバリデーション自体は通る。実害は小さい |
| 実装コスト | 低〜中。既存`FilePaths`型を再利用できるが、既存の`source_ref`との役割整理が必要（重複を許容するか、`source_ref`を`file_paths`に一本化するか） |
| 将来の検索性 | 低。ファイルパスへの検索需要は想定しにくい |
| **推奨** | **パターンA（`AssetMetaV0.file_paths: FilePaths`）。ただし`source_ref`との重複整理が前提条件（後述の残課題）** |

#### 3〜5. `creative_core.visuals` / `tone` / `ai_labels`

3項目とも`llm_response.CreativeCoreSchema`という1つの既存型に元々まとまっているため、まとめて比較する。

| 観点 | 内容 |
|---|---|
| source | LLM出力そのもの（`analysis_orchestrator.py` L526-528、`llm_response.CreativeCoreSchema.visuals`/`.tone`/`.ai_labels`） |
| パターンA | 該当性が低い。`asset_meta`は「取り込み時の事実」であり、`visuals`/`tone`/`ai_labels`はLLMによる解釈結果のため、asset/evaluation分割の設計思想（観測事実 vs 評価・解釈）に反する |
| パターンB | `EvaluationJsonV0`直下に3フィールド個別で追加することも可能だが、型を自作すると`CreativeCoreSchema`と重複定義になり、将来のドリフト（LLM出力側だけ変更されてevaluation_data側が追従しない）リスクを生む |
| パターンC | `EvaluationJsonV0.creative_core: CreativeCoreSchema`として、LLM出力の型をimportしてそのまま再利用。3フィールドすべてを1つの追加でカバーできる |
| backward compatibility | legacy側は`Optional[Dict[str, Any]]`（自由形状）のため、型を変えても影響は無い |
| 実装コスト | 低。新規型定義不要、既存`CreativeCoreSchema`を1フィールド追加するだけ |
| 将来の検索性 | 低〜中。将来`dominant_colors`等で検索したくなる可能性はあるが、現行の一覧・検索機能（`asset_id`/`format`等）と比べ優先度は低い |
| **推奨** | **パターンC（`EvaluationJsonV0.creative_core: CreativeCoreSchema`、3フィールドを1つのフィールドに内包）** |

#### 6. `creative_core.ocr_extracted_text`

| 観点 | 内容 |
|---|---|
| source | `OCRService.extract_text()`による**動画/画像全体**の単一OCRパス（`analysis_orchestrator.py` L282、L321-329）。**重要な確認事項**: `AssetStructureV0.ocr_segments`（カット単位の代表フレームOCR、`analysis_orchestrator.py` L219-239の`_OCRServiceForCuts.extract_text_from_image`）とは、フレームサンプリング方式自体が異なる**別々のOCR実行結果**であり、本バッチで実コードを確認した結果、一方から他方を機械的に再構成することはできないと判明した（前回PR #66時点では「部分的に近似可能」としていたが、より踏み込んだ確認により訂正） |
| パターンA | 該当性が低い。`asset_meta`の性質と合わない |
| パターンB | `AssetStructureV0`に新規フィールド（例: `whole_asset_ocr_text: str`）を追加。OCRはLLMの解釈を経ていない生テキスト＝「観測事実」であり、asset/evaluation分割の設計思想上、本来`asset_data`側に置くのが筋が通る |
| パターンC | 該当なし（`CreativeCoreSchema`に`ocr_extracted_text`は含まれない） |
| backward compatibility | legacy側は`str`必須（`default=""`）だが、**現行の`_populate_creative_core`自体がこの値を一切読んでおらず常に`""`**（PR #66調査で判明）。厳密な後方互換性より、今後正しく埋められるようにする方が実利がある |
| 実装コスト | 中。フィールド追加自体は低コストだが、`ocr_segments`という類似名称のデータが既にあるため、両者の違い（全体OCR vs カット単位OCR）をdocstringで明示する設計コミュニケーションコストが発生する |
| 将来の検索性 | 低。全文検索的な用途は現状想定されていない |
| **推奨** | **パターンB（`AssetStructureV0`に新規フィールド追加、asset_data側）。ただし`ocr_segments`との役割の違いをdocstringで明記することが前提** |

### 推奨案（1つに集約、未実装・要確認）

| 項目 | 推奨保存先 | 理由（要約） |
|---|---|---|
| `mode` | `AssetMetaV0.mode`（パターンA） | 取り込み時点の事実。既存`source_type`/`created_at`と同じ性質 |
| `file_paths` | `AssetMetaV0.file_paths`（パターンA） | 同上。ただし既存`source_ref`との重複整理が前提条件 |
| `visuals` | `EvaluationJsonV0.creative_core: CreativeCoreSchema`（パターンC） | LLM解釈結果。既存型の再利用でコスト最小、ドリフトリスクも低い |
| `tone` | 同上（`creative_core`に内包） | 同上 |
| `ai_labels` | 同上（`creative_core`に内包） | 同上 |
| `ocr_extracted_text` | `AssetStructureV0`に新規フィールド追加（パターンB、asset_data側） | 観測事実（生テキスト）であり評価結果ではない。`ocr_segments`とは別のOCR実行結果のため独立フィールドが必要 |

この推奨により、`asset_data`側（`AssetMetaV0`+`AssetStructureV0`）に3項目、`evaluation_data`側
（`EvaluationJsonV0`）に1項目（`creative_core`、3フィールドを内包）が追加される見込みとなる。
結果として、observed facts（`asset_data`）とinterpretation（`evaluation_data`）という
asset/evaluation分割の設計思想に沿った配置になっている。

### 残課題（この比較で新たに見えたもの、未確認）

- `AssetMetaV0.file_paths`（新規）と既存の`AssetMetaV0.source_ref`（単一文字列）の役割重複をどう
  整理するか（両方持つか、`source_ref`を将来的に廃止するか）は、フィールド追加時に別途決める必要がある。
- `AssetStructureV0`への`ocr_extracted_text`相当フィールド追加時、命名を`ocr_segments`と明確に
  区別できる名前にする（例: `whole_asset_ocr_text`）。

いずれも**未実装・未確認**。次バッチでユーザー確認を得たうえで、実際のPydanticフィールド追加
（コード変更）に着手する。`resolve_spec_data`へのwiringはさらにその後。

---

## ✅ 実装タスク（issue粒度）

1. **[設計]** 上記オープン課題1〜3を解決し、`spec_data`⇄(`asset_data`, `evaluation_data`)の完全なフィールド対応表を確定する — ✅ 完了（2026-07-09、`asset_v0.py`/`evaluation_v0.py`実装と同時）
2. **[実装]** `resolve_spec_data(spec_data, asset_data=None, evaluation_data=None) -> dict`を実装 — ✅ 完了（PR #61）。旧データ（spec_dataのみ）の無変換パスのみ実装。**新データ変換パス（downcast本体）は未実装**（オープン課題4・5が未解決のため、完全なdowncastはまだ書けない）
   - 2026-07-09追記: downcast第一バッチとして`_downcast_asset_meta()`を実装（`asset_meta`のみ対象、`resolve_spec_data`へは未配線）
3. **[テスト]** `resolve_spec_data`の単体テスト — 🟡 一部完了（PR #61）。「両方None→無変換」「片方/両方非None→fail-softフォールバック＋警告ログ」は実装・テスト済み。「合成テストデータでの実際のdowncast変換」は`_downcast_asset_meta()`のみ実装・テスト済み。`resolve_spec_data`全体の統合downcastテストはオープン課題4・5解決後
4. **[テスト]** `streamlit_app.py`のレンダリング関数が`resolve_spec_data`の新データ変換パス出力に対しても壊れずに表示できることの確認 — ⏳ 未着手（downcast本体が未実装のため対象がない）
5. **[組み込み判断]** `specs.py::get_spec`/`list_specs`への`resolve_spec_data`組み込み — ✅ 完了（2026-07-09、カラム追加と同じPRで実施）
6. **[ドキュメント]** 本ファイルの対応表を確定版として更新し、`docs/specs/`配下に正式スキーマドキュメントを作成 — 🟡 本ファイルの対応表は確定済み。`docs/specs/`配下への独立ドキュメント化はまだ未着手
7. **[Phase 1: カラム追加]** `AdInsight.asset_data`/`evaluation_data`カラム追加、Alembic導入 — ✅ 完了（2026-07-09）。`backend/alembic/`にbaseline+カラム追加の2マイグレーション、`backend/app/models/ad_insight.py`にカラム追加。**本番DBへの適用は未実施**（別途確認のうえ実施）
8. **[Phase 1: v0スキーマ]** `AssetJsonV0`/`EvaluationJsonV0`等の実装 — ✅ 完了（2026-07-09）。`backend/app/schemas/asset_v0.py`・`evaluation_v0.py`
9. **[downcast本体]** `asset_data + evaluation_data → spec_data`の実際の変換コード — 🟡 一部着手（2026-07-09）。`_downcast_asset_meta()`（`asset_meta`のみ）を実装・テスト済み、`resolve_spec_data`へは未配線。残り（`diagnostics`のvideo_cuts補完、および課題4・5解決後の`input_metadata`/`creative_core`）は次のバッチ

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
ステータス: Phase 1（カラム＋v0スキーマ）実装・ローカル検証済み、本番適用は未実施 ／ Phase 2 adapter scaffold・specs.py配線 実装済み ／ downcast第一バッチ（`_downcast_asset_meta`、未配線、PR #65マージ待ち）実装済み ／ オープン課題4・5の詳細調査（PR #66）＋6項目の保存方針比較・推奨案まで整理済み（docs-only、未確認・未実装）／ フィールド追加・downcast本体（完全版）・`resolve_spec_data`への配線はユーザー確認後に着手
