# JSON Schema — asset_data / evaluation_data (v0)

**Version**: v0（Phase 2 downcastバッチ2時点）
**Date**: 2026-07-09
**Status**: 🔵 スキーマ定義のみ完了、未使用（実データ生成は無し）
**対象カラム**: `AdInsight.asset_data` / `AdInsight.evaluation_data`（`backend/app/models/ad_insight.py`、nullable JSON）

---

## ⚠️ 現在地（重要）

このドキュメントが記述するのは **Pydanticスキーマの形のみ** であり、以下は含まない:

- **dual-write未実装**: `asset_data`/`evaluation_data`へ実際にデータを書き込むコードは存在しない（Phase 3）。現行の全レコードで両カラムは常に`NULL`。
- **downcast本体は部分実装のみ**: `backend/app/services/asset_evaluation_adapter.py`に
  `_downcast_asset_meta()`/`_downcast_input_metadata()`/`_downcast_creative_core()`
  （`spec_data`の`asset_meta`/`input_metadata`/`creative_core`ブロックのみ対応）は実装済みだが、
  `diagnostics`/`performance`/`landing_page`/`views`/`_metadata`は未対応。
  いずれの関数も`resolve_spec_data()`からはまだ呼ばれていない（未配線）。
- **本番DBへの`asset_data`/`evaluation_data`カラム追加マイグレーションは未適用**
  （`docs/DEPLOYMENT.md`「1a. DBマイグレーション」の手順に従い、別途明示指示のうえ実施）。

正本ドキュメントは `docs/plans/asset_evaluation_split_phase2_tasks.md`（設計判断の経緯・オープン課題・
実装タスクの進捗）。本ファイルはそこで確定したスキーマの「形」だけを、実装済みコードから抜粋・整理した
参照用ドキュメントという位置づけ。

---

## 📋 背景

現行`AdInsight.spec_data`（JSON正本、`docs/specs/ad_insight_json_schema_v0_2.md`）を、将来
「観測事実（`asset_data`）」と「評価・解釈（`evaluation_data`）」に分割するための準備として、
Phase 1で2つのnullableカラムを追加した。本ドキュメントはそのv0スキーマの現在の形を記述する。

---

## 📐 asset_data の構造（`AssetJsonV0`、`backend/app/schemas/asset_v0.py`）

```json
{
  "asset_meta": {
    "asset_id": "asset_20260709_local_summer01",
    "asset_name": "Summer Campaign Video v2",
    "platform": "meta",
    "ad_account_id": null,
    "campaign_name": "Summer 2026 Promo",
    "adset_name": null,
    "ad_name": null,
    "analysis_period": null,
    "external_ids": null,
    "source_type": "local_file",
    "source_ref": "/tmp/input.mp4",
    "created_at": "2026-07-09T12:00:00",
    "analysis_version": "v0",
    "mode": "file_plus_lp_plus_manual_kpi",
    "file_paths": {
      "creative_video": "/tmp/input.mp4",
      "creative_images": null,
      "landing_page_html": null
    }
  },
  "media_info": {
    "media_type": "video_static",
    "duration_seconds": 15.9,
    "width": 1080,
    "height": 1920,
    "fps": 30.0,
    "aspect_ratio": "9:16",
    "language": "ja"
  },
  "asset_structure": {
    "cuts": [
      {"cut_id": "cut_1", "start_sec": 0.0, "end_sec": 8.1}
    ],
    "transcript_segments": [
      {"text": "こんにちは", "start_sec": 0.0, "end_sec": 2.0}
    ],
    "ocr_segments": [
      {"text": "今だけ限定", "start_sec": 0.0, "end_sec": 5.0}
    ],
    "ocr_extracted_text": "動画全体の単一OCRパス結果（ocr_segmentsとは別データ）"
  },
  "asset_annotations": {
    "brand_mentions": ["ブランドA"],
    "product_mentions": [],
    "cta_candidates": [
      {"text": "今すぐ購入", "modality": "visual"}
    ],
    "people_presence": true,
    "voiceover_presence": null,
    "subtitle_presence": null
  }
}
```

### `asset_meta`（`AssetMetaV0`）

legacy `spec_data.asset_meta`（`AssetMeta`、`app/schemas/ad_insight.py`）の全フィールドを含む
スーパーセット（オープン課題1の解決方針）。**太字**はv0で新規追加したフィールド。

| フィールド | 型 | 必須 | 備考 |
|---|---|---|---|
| `asset_id` | str | ✅ | legacy asset_meta.asset_idと同一値、`^asset_[a-z0-9_]+$` |
| `asset_name` | str \| null | - | |
| `platform` | str \| null | - | |
| `ad_account_id` | str \| null | - | |
| `campaign_name` | str \| null | - | |
| `adset_name` | str \| null | - | |
| `ad_name` | str \| null | - | |
| `analysis_period` | `AnalysisPeriod` \| null | - | 既存型を再利用 |
| `external_ids` | `ExternalIds` \| null | - | 既存型を再利用 |
| `source_type` | `SourceTypeEnum` | ✅ | `local_file` / `api` / `hybrid` |
| `source_ref` | str \| null | - | 元ファイルパスや外部APIレスポンスIDなど、取り込み元への汎用参照 |
| `created_at` | datetime | ✅ | asset_data生成時刻 |
| `analysis_version` | str | ✅（default `"v0"`） | asset_data生成ロジックのバージョン |
| **`mode`** | `InputModeEnum` | ✅ | legacy `input_metadata.mode`への変換元。既存enumを再利用 |
| **`file_paths`** | `FilePaths` \| null | - | legacy `input_metadata.file_paths`への変換元。既存型を再利用。`source_ref`とは役割が異なる（後述） |

**`source_ref` と `file_paths` の使い分け**: `source_ref`は`source_type`が`api`/`hybrid`の場合も
含めた汎用的な単一参照（外部APIレスポンスID等）。`file_paths`は`source_type=local_file`時の
legacy互換の構造化パス（動画/画像リスト/LP HTML）。両方が同じパスを指す重複を許容する設計。

### `media_info`（`MediaInfoV0`）

| フィールド | 型 | 必須 | 備考 |
|---|---|---|---|
| `media_type` | `FormatEnum` | ✅ | legacy `creative_core.format`と同一語彙（変換不要） |
| `duration_seconds` | float \| null | - | legacy `creative_core.duration_seconds`への変換元 |
| `width` / `height` / `fps` / `aspect_ratio` / `language` | 各種 \| null | - | legacy側に対応フィールド無し（asset_data固有） |

### `asset_structure`（`AssetStructureV0`）

| フィールド | 型 | 備考 |
|---|---|---|
| `cuts` | `CutSpan[]` | カットの時間範囲。`diagnostics.video_cuts.video_cuts[].start_seconds/end_seconds`の一次情報源（オープン課題2の解決方針） |
| `transcript_segments` | `TranscriptSegment[]` | ASR文字起こし結果 |
| `ocr_segments` | `OcrSegment[]` | **カット単位**の代表フレームOCR結果 |
| **`ocr_extracted_text`** | str（default `""`） | legacy `creative_core.ocr_extracted_text`への変換元。**動画/画像全体**に対する単一OCRパスの結果で、`ocr_segments`とは別のOCR実行結果（`analysis_orchestrator.py`で実際に別呼び出しになっていることを確認済み。一方から他方を再構成することはできない） |

### `asset_annotations`（`AssetAnnotationsV0`）

legacy側に対応するブロックが無い、asset_data固有の新規annotation情報
（`brand_mentions`/`product_mentions`/`cta_candidates`/`people_presence`/`voiceover_presence`/`subtitle_presence`）。

---

## 📐 evaluation_data の構造（`EvaluationJsonV0`、`backend/app/schemas/evaluation_v0.py`）

```json
{
  "evaluation_meta": {
    "evaluated_at": "2026-07-09T12:30:00",
    "evaluator_model": "gpt-4o",
    "processing_time_ms": 4200,
    "validation_status": "passed",
    "validation_notes": ["LLM analysis: gpt-4o (success)"],
    "analysis_tools_used": {"ocr_engine": "tesseract"}
  },
  "diagnostics": { "...": "既存Diagnostics型（app/schemas/ad_insight.py）をそのまま再利用" },
  "performance": { "...": "既存Performance型をそのまま再利用（optional）" },
  "landing_page_analysis": { "...": "既存LandingPage型をそのまま再利用（optional）" },
  "creative_core": {
    "visuals": {
      "dominant_colors": ["#FF6B6B", "#FFFFFF"],
      "composition": "中央寄せの構図",
      "style": "モダン",
      "clarity": "高"
    },
    "tone": {
      "primary_tone": ["professional"],
      "emotional_appeal": "論理的",
      "call_to_action": "強"
    },
    "ai_labels": ["finance", "trust"]
  }
}
```

### `evaluation_meta`（`EvaluationMetaV0`）

legacy `spec_data._metadata`（`Metadata`）の9フィールドのうち、「評価実行時に確定する情報」を
持つ（オープン課題3の解決方針。「取り込み時に確定する情報」は`asset_meta`側）。

| フィールド | 型 | 必須 | legacy `_metadata`との対応 |
|---|---|---|---|
| `evaluated_at` | datetime | ✅ | - |
| `evaluator_model` | str | ✅ | `ai_model_version` |
| `processing_time_ms` | int \| null | - | `processing_time_ms` |
| `validation_status` | str \| null | - | `validation_status` |
| `validation_notes` | str[] \| null | - | `validation_notes` |
| `analysis_tools_used` | `AnalysisToolsUsed` \| null | - | `analysis_tools_used`（既存型を再利用） |

`json_schema_version`の復元方法はdowncast実装時の残課題（未決定）。

### `diagnostics` / `performance` / `landing_page_analysis`

新しい型を作らず、既存の`app.schemas.ad_insight`の型（`Diagnostics`/`Performance`/`LandingPage`）を
そのまま再利用する。評価結果の中身自体はasset/evaluation分割によって変わらないため。

### `creative_core`（**新規追加**、`llm_response.CreativeCoreSchema`を再利用）

| フィールド | 型 | 必須 | legacy `creative_core`との対応 |
|---|---|---|---|
| `visuals` | `VisualsSchema` | ✅ | `visuals` |
| `tone` | `ToneSchema` | ✅ | `tone` |
| `ai_labels` | str[] | ✅ | `ai_labels` |

`EvaluationJsonV0.creative_core`自体は`Optional[CreativeCoreSchema]`（未設定時`None`）。
新しい型を自作せず、`app.schemas.llm_response.CreativeCoreSchema`
（`analysis_orchestrator.py`が実際にLLM結果を格納する際に使っている型と同一）をそのまま再利用する。
`format`/`duration_seconds`は`asset_data.media_info`側に既にあり、
`primary_text`/`headline`/`body_text`/`call_to_action`/`platform_specific`はlegacy側でも
常に`None`（未実装）のため、ここには含まれない。

---

## 🔗 legacy spec_data との対応表（downcast方針の要約）

詳細は`docs/plans/asset_evaluation_split_phase2_tasks.md`の変換方針テーブルを正本とする。要約:

| legacy `spec_data`キー | 変換元 | downcast実装状況 |
|---|---|---|
| `asset_meta` | `asset_data.asset_meta` | ✅ `_downcast_asset_meta()`実装済み（未配線） |
| `input_metadata` | `asset_data.asset_meta`（`mode`/`source_type`/`created_at`/`file_paths`） | ✅ `_downcast_input_metadata()`実装済み（未配線） |
| `creative_core` | `asset_data.media_info` + `asset_data.asset_structure` + `evaluation_data.creative_core` | ✅ `_downcast_creative_core()`実装済み（未配線） |
| `diagnostics` | `evaluation_data.diagnostics` + `asset_data.asset_structure.cuts`（video_cuts補完） | ⏳ 未実装 |
| `performance` | `evaluation_data.performance` | ⏳ 未実装（型はそのまま転記可能、関数化はまだ） |
| `landing_page` | `evaluation_data.landing_page_analysis` | ⏳ 未実装（同上） |
| `views` | （変換元なし、Optionalのため省略可） | ⏳ 未実装 |
| `_metadata` | `asset_data.asset_meta` + `evaluation_data.evaluation_meta` | ⏳ 未実装（`json_schema_version`の復元方法が未決定） |

---

## 🔗 関連ドキュメント

- `docs/plans/asset_evaluation_split_phase2_tasks.md` — 設計判断の正本、進捗管理
- `docs/specs/ad_insight_json_schema_v0_2.md` — legacy `spec_data`のトップレベル構造
- `backend/app/schemas/asset_v0.py` / `evaluation_v0.py` — 実装本体
- `backend/app/services/asset_evaluation_adapter.py` — downcast実装本体
- `backend/tests/test_asset_v0_schema.py` / `test_asset_evaluation_adapter.py` — 単体テスト

最終更新: 2026-07-09
