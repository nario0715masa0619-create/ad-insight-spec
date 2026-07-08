# Asset/Evaluation Split — Phase 2: Read Adapter / Upcaster 設計

**対象フェーズ**: Phase 2（read adapter設計のみ、dual-write実装は含まない）
**前提**: Phase 1（`AdInsight.asset_data`/`evaluation_data`カラム追加、`AssetJsonV0`/`EvaluationJsonV0`スキーマ定義）は Antigravity 側のローカルブランチ（`feature/asset-evaluation-split-phase1`、未push）で実装中。本ドキュメントはそのレビュー内容を踏まえて作成。
**ステータス**: 🔵 Planning

---

## 📋 背景・目的

現在`AdInsight`は`spec_data`（JSON正本、`ad_insight_spec v0.2`全体）1カラムに全データを持つ設計。Phase 1でこれを将来的に「観測事実（asset_data）」と「評価・解釈（evaluation_data）」に分割する準備として、2つのnullableカラムを追加した。

Phase 2の目的は、**dual-write（両カラムへの実書き込み）を始める前に、読み出し側の抽象化（adapter）を先に固める**こと。これにより:
- dual-writeが始まった後も、既存UI（`streamlit_app.py`）・既存API（`GET /specs/{asset_id}`等）が一切変更を必要としない
- 新旧データ形状（`spec_data`のみの行 / `asset_data`+`evaluation_data`が入った行）が混在する移行期間を安全に扱える
- Phase 3（dual-write実装）が始まる前に、変換ロジックのテストとレビューを完了できる

**このPhaseではコードは書かず、設計と実装タスクの分解のみを行う。**

---

## 🎯 Read Adapter の責務

### 1つの入口関数として設計する

```python
def resolve_spec_data(record: AdInsight) -> dict:
    """
    AdInsightレコード1件から、既存のspec_data形状（ad_insight_spec v0.2互換）の
    dictを返す。呼び出し側（specs.pyのAPIハンドラ）はこの関数の戻り値だけを見れば
    よく、record.asset_data/evaluation_dataが実際に入っているかどうかを意識しない。
    """
```

判定ロジック（feature flagは不要、レコード自身の状態がそのまま切替条件になる）:

| `asset_data` | `evaluation_data` | 挙動 |
|---|---|---|
| null | null | `record.spec_data`をそのまま返す（現状の全レコードがこれ。無変更） |
| 値あり | 値あり | `asset_data`+`evaluation_data`から`spec_data`互換dictを **再構築** して返す（downcast） |
| 値あり | null（またはその逆） | 不整合データとみなし、`record.spec_data`側にフォールバック（fail-soft。ログに警告を出す） |

この「レコード自身の状態がそのまま分岐条件」という設計は、本セッションで実装済みの`video_cuts`の新旧形状判定（`diagnostics.video_cuts`に`generation_status`キーがあるか否かで新旧を判定する、`frontend/streamlit_app.py::render_asset_detail`）と同じパターンであり、このリポジトリで既に実績のある方式。新規のfeature flag機構は導入しない。

### downcast（`asset_data + evaluation_data → legacy spec_data`）の変換方針

| legacy `spec_data`のキー | 変換元 | 備考 |
|---|---|---|
| `asset_meta` | `asset_data.asset_meta`（`AssetMetaV0`） | **要解決**: `AssetMetaV0`には`platform`/`campaign_name`/`adset_name`/`ad_name`/`analysis_period`/`external_ids`が無い。これらはnull埋めするか、Phase 1側で`AssetMetaV0`に追加するか要判断（下記オープン課題参照） |
| `creative_core.format` | `asset_data.media_info.media_type` | `video`→`video_static`等のマッピング要定義 |
| `creative_core.duration_seconds` | `asset_data.media_info.duration_seconds` | そのまま |
| `diagnostics` | `evaluation_data.diagnostics` | `EvaluationJsonV0.diagnostics`は既存`Diagnostics`型をそのまま再利用しているため、実質そのまま転記可能 |
| `diagnostics.video_cuts.video_cuts[].start_seconds/end_seconds` | `asset_data.asset_structure.cuts[]`（`CutSpan`、`cut_id`で結合） | **要解決**: `evaluation_data.diagnostics.video_cuts`が独自に`start_seconds`/`end_seconds`を持つか、`asset_data`側の`CutSpan`だけを正とするか統一する（現状は両方が同じ情報を持ちうる二重管理になっている） |
| `performance` | `evaluation_data.performance` | そのまま |
| `landing_page` | `evaluation_data.landing_page_analysis` | そのまま |
| `_metadata` | `asset_data.asset_meta.analysis_version` + `evaluation_data.evaluation_meta` | 新旧のバージョン情報を`_metadata.json_schema_version`相当にどうまとめるか要定義 |

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

呼び出し箇所: `specs.py`の`get_spec`/`list_specs`内、現在`record.spec_data`を直接使っている箇所を`resolve_spec_data(record)`に置き換える（Phase 2ではこの置き換え自体もまだ実施しない。関数を実装しテストするところまでに留め、実際の呼び出し箇所への組み込みはPhase 3の一部として実施するか、Phase 2の最終タスクとして早めに組み込むかは実装時に判断する。ただし組み込んだ時点でも旧データの挙動は無変換のため、リリースリスクは低い）。

---

## 🚩 feature flag / 切替条件

不要。上記のとおり、レコードの`asset_data`/`evaluation_data`がnullかどうかがそのまま切替条件になる。環境変数やDB設定によるON/OFFフラグは導入しない（切替のための追加の状態を持たない方が、移行期間中の挙動予測がしやすい）。

---

## ⚠️ Phase 2着手前に解決すべきオープン課題

1. **`asset_meta`の名称衝突**: `AssetMetaV0`と既存`AssetMeta`（`app/schemas/ad_insight.py`）が同名で別構造。ドキュメント・コード上の呼称を明確に区別する（例: 「v0 asset_meta」「legacy asset_meta」）か、`AssetMetaV0`に欠落フィールドを追加するかを先に決める。
2. **カット情報の一次情報源**: `asset_data.asset_structure.cuts`（境界のみ）と`evaluation_data.diagnostics.video_cuts.video_cuts[]`（`start_seconds`/`end_seconds`を含む、LLM評価付き）の二重管理をどう解消するか。推奨: `asset_data`側を一次情報源とし、`evaluation_data`側は`cut_id`のみ保持して`start_seconds`/`end_seconds`はadapterが`asset_data`から補完する（現行の`VideoCutContent`が「LLMには時間範囲を再生成させず、バックエンド確定値をマージする」設計を踏襲している点と一貫性がある）。
3. **`_metadata`相当情報の再構成方針**: `json_schema_version`・`ai_model_version`等を新形状のどこから復元するか。

---

## ✅ 実装タスク（issue粒度）

1. **[設計]** 上記オープン課題1〜3を解決し、`spec_data`⇄(`asset_data`, `evaluation_data`)の完全なフィールド対応表を確定する
2. **[実装]** `backend/app/services/asset_evaluation_adapter.py`に`resolve_spec_data(record: AdInsight) -> dict`を実装（旧データはそのまま返すパスのみ、新データ変換パスも実装するが実際に新データが存在しないため単体テストのみで検証）
3. **[テスト]** `resolve_spec_data`の単体テスト:
   - `asset_data`/`evaluation_data`が両方Noneの場合、`spec_data`をそのまま返すこと
   - 両方に値がある合成テストデータで、既存`AdInsightSpec`のバリデーションを通る形状に変換できること
   - 片方だけ値がある不整合ケースでfail-softに`spec_data`へフォールバックし、警告ログが出ること
4. **[テスト]** 既存の`streamlit_app.py`のレンダリング関数（`render_asset_detail`等）が、`resolve_spec_data`の出力（新データ変換パス側）に対しても壊れずに表示できることを確認する統合テスト、またはローカル実ブラウザでの目視確認
5. **[組み込み判断]** `specs.py::get_spec`/`list_specs`への`resolve_spec_data`組み込みタイミングを決定（Phase 2内で組み込むか、Phase 3のdual-write実装と同時にするか）
6. **[ドキュメント]** 本ファイルの対応表を確定版として更新し、`docs/specs/`配下に正式スキーマドキュメント（`ad_insight_json_schema_v0_2.md`・`video_cuts_json_schema_v1_0.md`と同じ形式）を作成
7. **[Phase 1側への差し戻し事項]** `alembic.ini`の`sqlalchemy.url`が相対パス（`sqlite:///./ad_insight.db`）になっている件の修正（Phase 1レビューで指摘済み、Phase 2着手前に解決を推奨）

---

## 🔗 関連ドキュメント

- `docs/specs/ad_insight_json_schema_v0_2.md` — 現行`spec_data`のトップレベル構造
- `docs/specs/video_cuts_json_schema_v1_0.md` — 新旧形状判定パターンの先行事例（`generation_status`キーの有無による判定）
- `backend/app/models/ad_insight.py` — Phase 1で`asset_data`/`evaluation_data`カラムを追加（Antigravity側ローカルブランチ、未push）

最終更新: 2026-07-08
ステータス: Planning（オープン課題の解決待ち）
