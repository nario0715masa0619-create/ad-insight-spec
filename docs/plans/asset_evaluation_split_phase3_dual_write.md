# Asset/Evaluation Split — Phase 3: Dual-Write 設計

**対象フェーズ**: Phase 3（`asset_data`/`evaluation_data`への実書き込み、dual-write）
**前提**: Phase 2（read adapter）はPR #71で実装完了・配線済み。`asset_data`/`evaluation_data`カラムはPhase 1（PR #63）で追加済みだが、**本番DBへの適用はまだ実施していない**。
**ステータス**: 🔵 Planning（**本ドキュメントはdocs-only。コード変更は一切含まない**）

---

## 📋 背景・目的

Phase 1で`AdInsight.asset_data`/`evaluation_data`カラムを追加し、Phase 2でそれらを読み出す
adapter（`resolve_spec_data`）を実装・配線した。しかし、これらのカラムに実際に値を
書き込むコードはまだ存在しない（現行の全レコードは常に両方`NULL`）。Phase 3の目的は、
**分析実行時（`POST /analyze`）に`spec_data`と同時に`asset_data`/`evaluation_data`も
構築・保存する（dual-write）**ようにすることで、Phase 2の読み出しパスを実データで
初めて検証可能にすること。

**このドキュメントでは設計のみを行い、コードは書かない。** 実装は本ドキュメントの
「📦 最小実装単位の提案」で分割した、複数の小さいPRに分けて別途進める。

---

## 🔍 1. 現行の書き込み経路調査

### 1.1 `spec_data`構築〜保存までのフロー（実コード確認済み）

```
POST /analyze（backend/app/api/routes/specs.py::analyze）
  └─ AnalysisOrchestrator(...).run()（backend/app/services/analysis_orchestrator.py）
       ├─ _step_ingest()            → self.ingested_asset
       ├─ _step_metadata()          → self.metadata
       ├─ _step_content_analysis()  → self.video_result / self.ocr_result / self.lp_result /
       │                               self.video_cuts / self.ocr_coverage_ratio / self.asr_result
       ├─ _step_llm()               → self.llm_result
       ├─ _step_load_kpi()（optional）→ self.kpi_data
       ├─ _step_converter()         → ConverterService.execute(...) → self.final_spec
       └─ processing_time_ms を計算し self.final_spec["_metadata"] に注入 → return self.final_spec
  └─ AdInsightSpec(**spec_dict)   # Pydantic v0.2 バリデーション（既存、変更しない）
  └─ json.loads(spec.json())     # spec_data_jsonable（datetime安全化を経由済み）
  └─ AdInsightRepository(db).create(asset_id, format, spec_data=spec_data_jsonable)
       # ← 実コード全体で唯一のDB書き込み点
```

### 1.2 `repo.create()`の呼び出し箇所は1つだけ

`grep`で確認した結果、`AdInsightRepository.create()`を呼んでいるのは
`backend/app/api/routes/specs.py::analyze`（本番コード）と`backend/tests/test_repositories.py`
（テスト）の2箇所のみ。他にDBへ`spec_data`を書き込む経路は存在しない。

### 1.3 CLI（`backend/app/cli/main.py`）はDBに一切触れない

CLIの`analyze`コマンドも`orchestrator.run()`を呼ぶが、戻り値をそのままJSONファイルへ
書き出すだけで、DBは一切使わない。**dual-write実装はCLIパスに影響しない**
（`orchestrator.run()`の戻り値・シグネチャを変えない限り）。

---

## 🎯 2. dual-writeの書き込みポイント（特定結果）

新たにDBへ書き込む処理を追加すべき場所は、`backend/app/api/routes/specs.py`の
`repo.create()`呼び出し（1箇所）のみ。ここに`asset_data`/`evaluation_data`を渡せるように
拡張することが、dual-write実装のゴール。

---

## 🏗 3. asset_data / evaluation_data 構築方針の設計

### 3.1 重要な設計原則: `self.final_spec`から流用できるものは流用する

`ConverterService`は既に`spec_data`の各セクションを構築済みであり、そのうち
**`asset_meta`・`creative_core.format`/`duration_seconds`・`diagnostics`・`performance`・
`landing_page`は、v0スキーマ側でも「legacy型をそのまま再利用」または
「legacy側と共有フィールド」として設計されている**（Phase 2のオープン課題1・
6項目の保存方針比較で確定済み）。

つまり、これらは生の中間結果（`ingestion_result`等）から**再度構築する必要がない**。
`self.final_spec`（構築済みの`spec_data`）から値を転記するだけで済む。これにより:

- 新規コードが最小限になる
- `spec_data`とasset_data/evaluation_dataの間で値が食い違う（ドリフトする）リスクが
  構造的に排除される（同じ値を2箇所で独立に計算しない）

| v0スキーマ側フィールド | 値の出所 |
|---|---|
| `asset_data.asset_meta`の共通9フィールド（`asset_id`/`asset_name`/`platform`等） | `self.final_spec["asset_meta"]`から転記 |
| `asset_data.media_info.media_type`/`.duration_seconds` | `self.final_spec["creative_core"]["format"]`/`["duration_seconds"]`から転記 |
| `evaluation_data.diagnostics` | `self.final_spec["diagnostics"]`をそのまま転記（型が完全一致のため） |
| `evaluation_data.performance` | `self.final_spec["performance"]`をそのまま転記 |
| `evaluation_data.landing_page_analysis` | `self.final_spec["landing_page"]`をそのまま転記 |
| `evaluation_data.evaluation_meta.processing_time_ms`/`.validation_status`/`.validation_notes`/`.analysis_tools_used` | `self.final_spec["_metadata"]`から転記（`_populate_metadata`が既に算出済み） |

残りの、`spec_data`に存在しないv0専用フィールドだけを新規に構築する:

| v0スキーマ側フィールド | 値の出所（新規構築） |
|---|---|
| `asset_meta.source_type` | 固定値`"local_file"`（legacyの`_populate_input_metadata`と同じ） |
| `asset_meta.source_ref` | `self.input_path` |
| `asset_meta.created_at` | `datetime.now()` |
| `asset_meta.analysis_version` | 固定値`"v0"` |
| `asset_meta.mode` | `self.mode` |
| `asset_meta.file_paths` | `self.ingested_asset`から構築（legacyの`_populate_input_metadata`と同じロジック） |
| `asset_structure.cuts` | `self.video_cuts`（`cut_id`/`start_seconds`/`end_seconds`→`CutSpan`） |
| `asset_structure.ocr_extracted_text` | `self.ocr_result.get("ocr_extracted_text", "")` |
| `asset_structure.ocr_segments` / `.transcript_segments` | **今回は空リストのまま**（下記3.4「今回のスコープに含めない項目」参照） |
| `asset_annotations`（brand_mentions等） | **今回は全てデフォルト値（空リスト/None）のまま**（同上） |
| `evaluation_meta.evaluated_at` | `datetime.now()` |
| `evaluation_meta.evaluator_model` | `self.llm_result["creative_core"].get("llm_model")` |
| `evaluation_data.creative_core`（`visuals`/`tone`/`ai_labels`） | `self.llm_result["creative_core"]`から転記 |

### 3.2 責務をどのserviceに置くか（確認したい論点への回答）

**推奨: 新規service `backend/app/services/asset_evaluation_builder_service.py` を追加する。**

理由:
- `ConverterService`は「入力材料 → `spec_data`を新規構築する」という既存の確立された
  責務を持つ。asset_data/evaluation_dataは別の出力形状であり、`ConverterService`に
  混ぜると1つのクラスが2つの異なる出力形状を担うことになり責務が肥大化する
  （Phase 2の「どの層に置くか」での`resolve_spec_data`の配置判断と対称的な理由）。
- 前述のとおり、この新serviceの主な仕事は「`self.final_spec`から転記」＋「わずかな
  新規フィールドの構築」であり、`ConverterService`を直接呼び出す必要はない
  （`ConverterService`の出力＝`self.final_spec`を受け取るだけでよい）。
- `ConverterService`の`_populate_*`群と同じ「複数の小さい構築メソッド」パターンを
  踏襲し、`build_asset_data(...)`/`build_evaluation_data(...)`という2つの公開メソッドを
  持たせる。

### 3.3 どこから呼ぶか（オーケストレーション）

**推奨: `AnalysisOrchestrator.run()`の最後（`processing_time_ms`注入の直後、
`return`の直前）に新しいステップを追加する。**

理由:
- `evaluation_meta.processing_time_ms`は`self.final_spec["_metadata"]["processing_time_ms"]`
  から転記する設計（3.1参照）だが、この値は`run()`内で`_step_converter()`の**後**に
  計算・注入される。したがって、新ステップは`_step_converter()`の中ではなく、
  `run()`本体でこの注入が終わった後に呼ぶ必要がある。
- `AnalysisOrchestrator`は既に全ての中間結果（`self.ingested_asset`/`self.metadata`/
  `self.llm_result`/`self.video_cuts`等）を保持している唯一の場所。ここに新しい
  呼び出しを足すのが最小の変更。
- `run()`の戻り値（`self.final_spec`のみを返す）は**変更しない**。CLIは`run()`の
  戻り値だけを見ており、DBには触れないため影響が無い（1.3参照）。
- 新しいインスタンス属性`self.asset_data`/`self.evaluation_data`を追加し、
  `get_asset_data()`/`get_evaluation_data()`という新しいgetterを追加する
  （既存の`get_spec()`と同じパターン）。`specs.py`側は`orchestrator.run()`の後に、
  これら2つの新しいgetterを呼んで`repo.create()`に渡す。

### 3.4 fail-soft方針（dual-writeが失敗しても`spec_data`保存は成功させる）

**推奨: asset_data/evaluation_data構築が失敗しても、`spec_data`保存自体は失敗させない。**

理由: `spec_data`は引き続き唯一のsource of truthであり、これまでの分析結果保存の
信頼性を一切下げてはならない。構築中に例外が発生した場合は、警告ログを出したうえで
`None`のまま保存する（＝そのレコードは実質的に「まだ`spec_data`のみ」として扱われ、
Phase 2の`resolve_spec_data`は通常どおりpassthroughする）。これは分析パイプライン
全体で既に確立されているfail-soft方針（OCR/LLM/ASR等の失敗時と同じパターン、
`analysis_orchestrator.py`の`except Exception: logger.warning(...)`群）と一貫性がある。

### 3.5 datetime JSON化の既知の落とし穴への対応

新serviceの`build_asset_data`/`build_evaluation_data`は、内部で`AssetJsonV0(...)`/
`EvaluationJsonV0(...)`を構築し、`.dict()`ではなく`json.loads(model.json())`を経由して
dictを返す（`asset_v0.py`/`evaluation_v0.py`のモジュールdocstringで既に警告済みの
パターンをそのまま踏襲、本セッション中に実際に2回踏んだ既知バグの再発防止）。
呼び出し側（orchestrator/specs.py）はこの変換を意識しなくてよい。

### 3.6 今回のスコープに含めない項目（v0専用の新規観測データ）

`asset_structure.ocr_segments`/`.transcript_segments`（カット単位OCR・ASR文字起こしの
セグメント化）、`asset_annotations`（`brand_mentions`/`cta_candidates`等）は、
**現行のいずれのserviceからも、この粒度のデータを直接取得できない**
（`self.video_cuts`はカット単位のOCRテキストを持つが`OcrSegment`が要求する
`start_sec`/`end_sec`との対応はcut境界と同じにできるため技術的には可能だが、
`transcript_segments`・`asset_annotations`は対応する生データが現行パイプラインに
一切存在しない）。これらは**Phase 3の最小実装では空リスト/デフォルト値のまま**とし、
将来の拡張候補として明記するに留める（`ocr_segments`は`self.video_cuts`から
機械的に構築できるため、実装コストが低ければPR Bの範囲に含めてもよい判断材料として
残す）。

---

## 🔀 4. 既存`spec_data`との併存期間の扱い（確認したい論点への回答）

- `spec_data`は**引き続き唯一の書き込み時バリデーション対象**（`AdInsightSpec(**spec_dict)`
  は今までどおり実施し続ける）。dual-writeはこれに「追加」するだけで、置き換えない。
- 併存期間に終了予定日は設けない。「`asset_data`/`evaluation_data`だけを正本にして
  `spec_data`書き込みをやめる」という判断は、Phase 3のスコープ外の将来判断
  （仮にPhase 4）として明確に切り離す。
- 読み出し側（Phase 2の`resolve_spec_data`）は既に「`asset_data`/`evaluation_data`が
  `None`なら無変換、両方あればdowncast」という設計になっているため、併存期間中に
  新旧レコードが混在しても矛盾なく動作する（Phase 2で既にテスト済みの前提。
  PR #71の`TestResolveSpecDataFullDowncastIntegration`が、legacy `AdInsightSpec`への
  バリデーションまで通ることを確認済み）。

---

## 🖥 5. `streamlit_app.py`の確認タイミング（確認したい論点への回答）

- **今回のPhase 3実装バッチでは、`streamlit_app.py`側のコード変更は不要**。
  フロントエンドは常に`GET /specs`系APIのレスポンス（＝`spec_data`互換の形）しか
  見ておらず、それは`resolve_spec_data`により新旧レコードとも同じ形に正規化される
  ため（Phase 2で既に配線・検証済み）。
- ただし目視確認は必要。推奨タイミング・手順:
  1. ローカルでマイグレーション適用（`alembic upgrade head`、devDB）
  2. dual-write実装（下記PR D・E）をローカルに適用
  3. 実際に`POST /analyze`を1回実行し、新規レコードの`asset_data`/`evaluation_data`が
     実際に保存されることをDB上で確認
  4. `GET /specs/{asset_id}`のレスポンスが、`resolve_spec_data`経由で`spec_data`直接
     書き込み時と同じ形になることを確認
  5. 実ブラウザでStreamlit UIの一覧・詳細表示が新規レコードでも壊れずに表示される
     ことを確認（CLAUDE.mdのStreamlit一覧UI観点・実ブラウザ確認必須の方針に沿う）
- 本番導入前の最終確認としても、本番マイグレーション適用後に同様の手順を踏む。

---

## 🚦 6. migration適用前後で壊れない実装順序（確認したい論点への回答）

Phase 1の`docs/DEPLOYMENT.md`「1a. DBマイグレーション」で確立した
「**マイグレーション適用 → コードデプロイ**」の順序を、Phase 3のdual-writeコードにも
そのまま適用する。

新コード（`repo.create()`の新パラメータ、orchestrator拡張）は、`asset_data`/
`evaluation_data`カラムの存在を前提にしたINSERT操作を行う。カラムが無い本番DBに
対して新コードを先にデプロイすると、Phase 1で実際に確認したのと同じ種類の
`OperationalError`（今回はSELECTではなくINSERT時）が発生し、`/analyze`が全面的に
失敗する重大な障害になる。

推奨順序:
1. ローカル/devで新コードを実装・テスト（Phase 1で既に`alembic upgrade head`済みの
   devDBを使う）
2. 本番マイグレーション適用（`docs/DEPLOYMENT.md`の手順どおり、バックアップ→
   `alembic stamp`→`alembic upgrade head`）— **これは別タスク、明示指示待ち**
3. マイグレーション適用確認後、dual-write実装済みの新コードを本番デプロイ
4. 本番で実際に`/analyze`を1回実行し、新規レコードの`asset_data`/`evaluation_data`が
   保存されることを確認

**今回のスコープでは3・4は実施しない**（本番migration/deployは引き続き行わない、
という前提を遵守する）。

---

## 📦 7. 最小実装単位の提案（複数の小さいPRへの分割案）

優先順位つきで、以下のように分割することを提案する。各PRは独立してレビュー・
マージ可能な単位で、Phase 2で確立した「小さなバッチで進める」進め方を踏襲する。

### PR A（本ドキュメント、docs-only）
今回のタスクの成果物。コード変更なし。

### PR B: `AssetEvaluationBuilderService`の新規実装＋単体テスト（配線なし）
- `backend/app/services/asset_evaluation_builder_service.py`を新規作成
- `build_asset_data(spec_data, mode, input_path, ingested_asset, video_cuts, ocr_result) -> Dict[str, Any]`
- `build_evaluation_data(spec_data, llm_result) -> Dict[str, Any]`
  （引数名・シグネチャは実装時に確定。3.1の表が示す「`spec_data`から転記」「新規構築」の
  切り分けをそのまま実装する）
- 単体テスト（合成データで`AssetJsonV0`/`EvaluationJsonV0`のPydanticバリデーションを
  通ることを確認。Phase 2 PR #71の`TestResolveSpecDataFullDowncastIntegration`と
  対になるテスト）
- **オーケストレーター・API層への配線は行わない**（Phase 2のバッチ構成と同じ、
  実装とテストのみに絞る）

### PR C: `AdInsightRepository.create()`への`asset_data`/`evaluation_data`パラメータ追加（配線なし）
- デフォルト`None`の追加パラメータのみ。既存呼び出し元は無変更で動作継続。
- 単体テスト（新パラメータを渡した場合／渡さない場合の両方を確認）

### PR D: `AnalysisOrchestrator`の拡張（`self.asset_data`/`self.evaluation_data`保持、getter追加）
- `run()`の`processing_time_ms`注入後・`return`前に、`AssetEvaluationBuilderService`を
  呼び出し、結果を`self.asset_data`/`self.evaluation_data`に保持
- 構築失敗時はfail-soft（警告ログ＋`None`のまま、`run()`自体は成功させる）
- `run()`の戻り値・CLIの挙動は無変更
- 単体テスト（正常系・fail-soft系）

### PR E: `specs.py`の`/analyze`配線（実際のdual-write開始）
- `repo.create()`呼び出しに`asset_data`/`evaluation_data`を追加
- **この時点で初めて、実際にDBへ`asset_data`/`evaluation_data`が書き込まれるように
  なる**
- ローカル環境でのend-to-end確認（マイグレーション適用済みのdevDBに対し、実際に
  `/analyze`を実行）
- 実ブラウザでのStreamlit確認（上記5参照）

### PR F（別タスク）: 本番マイグレーション適用＋デプロイ
- 明示指示後に別途実施
- `docs/DEPLOYMENT.md`の手順に厳密に従う（バックアップ→`alembic stamp`→
  `alembic upgrade head`→コードデプロイ→動作確認）

**今回のバッチではPR A（本ドキュメント）のみを作成する。** PR B以降は、本ドキュメントの
レビュー後、個別に着手する。

---

## 🔗 関連ドキュメント

- `docs/plans/asset_evaluation_split_phase2_tasks.md` — Phase 2（read adapter）の設計・実装記録
- `docs/specs/asset_evaluation_v0_schema.md` — `asset_data`/`evaluation_data` v0スキーマの現在の形
- `docs/DEPLOYMENT.md`（「1a. DBマイグレーション」） — マイグレーション適用手順・実施順序
- `backend/app/services/converter_service.py` — `spec_data`構築ロジック（流用元）
- `backend/app/services/analysis_orchestrator.py` — パイプライン全体のオーケストレーション
- `backend/app/api/routes/specs.py` — `POST /analyze`、唯一のDB書き込み点
- `backend/app/repositories/ad_insight_repository.py` — `create()`

最終更新: 2026-07-09
ステータス: Planning（docs-only）。次のアクション: 本ドキュメントのレビュー後、PR Bから着手
