# Asset/Evaluation Split — P1: 生成ロジック実装（asset_data/evaluation_data）

**対象**: `docs/plans/asset_evaluation_split_phase2_tasks.md`（Phase 1=DBカラム+v0スキーマ、Phase 2=read adapter設計）とは別軸の作業。
Phase 2の read adapter（`resolve_spec_data`のdowncast本体）はこのリポジトリではまだ未マージのため、本作業はそれに依存せず、
**main にマージ済みの Phase 1（`asset_v0.py`/`evaluation_v0.py`、`asset_data`/`evaluation_data`カラム）のみを土台**にしている。

**ステータス**: 🟢 実装済み・ローカルテスト green

## スコープ

1. `ConverterService`に `AssetJsonV0`/`EvaluationJsonV0` の生成ロジック（`_build_asset_evaluation_v0`）を追加し、
   `execute()`の戻り値に `asset_data`/`evaluation_data`（JSON-safe dict、生成失敗時はfail-softで両方None）を含める。
2. `AnalysisOrchestrator`: `self.video_cuts`（カット別タイミング+OCR）を`ConverterService.execute()`に配線し、
   `run()`完了後に`_metadata.processing_time_ms`と同じタイミングで`evaluation_data.evaluation_meta.processing_time_ms`も実測値で上書きする。
3. `POST /analyze`（`specs.py`）: `asset_data`/`evaluation_data`をAPIレスポンスに含める。**DB保存（`repo.create()`）はspec_dataのみで変更していない**（dual-writeはこの作業のスコープ外）。
4. CLI（`analyze`コマンド）: `orchestrator.run()`の戻り値をそのまま出力するため、変更なしで`asset_data`/`evaluation_data`が出力JSONに含まれる。

## 明示的にスコープ外（今回は捏造しない）

- `asset_data.asset_structure.transcript_segments`: 常に空リスト。現行`ASRService.transcribe()`はセグメント単位の
  テキスト+タイムスタンプを保持しない（`speech_duration_seconds`のみ集計）ため、honestに埋められる情報源がない。
- `asset_data.asset_annotations`（brand_mentions/product_mentions/cta_candidates/people_presence等）: 常にデフォルト（空/None）。
  現行パイプラインはこれらを構造化検出していない（`ai_labels`は自由形式タグのみで、ブランド/CTA判定には使えない）。
- `asset_data.media_info.aspect_ratio`: 常にNone。width/heightから比率文字列（例: "9:16"）を算出するロジックは未実装。
- DBへのdual-write（`asset_data`/`evaluation_data`カラムへの実書き込み）は行っていない。書き込み対象は引き続き`spec_data`のみ。

これらは将来、ASRのセグメント単位出力・ブランド/CTA検出・aspect_ratio算出が実装された時点で拡張する。

## 副次的に見つかった既存バグの修正

`backend/app/cli/main.py`の`json.dump(spec, f, ...)`は、`ConverterService`が`spec.dict()`（`.json()`ではない）で
戻り値を組み立てているため、`input_metadata.input_timestamp`等のdatetimeフィールドが生のPythonオブジェクトのまま残り、
**この作業以前から**CLI実行時に`TypeError: Object of type datetime is not JSON serializable`で失敗する構造だった
（`backend/tests/test_orchestrator_asset_evaluation_wiring.py`のCLI出力検証テストで発覚）。
`json.dump(..., default=str)`で保険をかけて修正した。新設の`asset_data`/`evaluation_data`自体は
`json.loads(model.json())`経由で既にJSON-safeなため、`default=str`には依存していない。

## テスト

- `backend/tests/test_converter_service.py`: `_build_asset_evaluation_v0`の単体テスト
  （フル入力/`file_only`最小入力、寸法パース、fail-soft、JSON直列化）。
- `backend/tests/test_orchestrator_asset_evaluation_wiring.py`: `AnalysisOrchestrator.run()`レベルの配線テスト
  （`video_cuts`の伝播、`processing_time_ms`の後上書き、CLI相当のJSON直列化）。
- 既存テストスイートに回帰なし（`test_llm_service.py`の4件はGPT/Gemini一貫性テストの既知の無関係な失敗）。
