# Architecture Design - Phase 1: File-First Strategy

**Version**: 1.0  
**Date**: 2026-06-23  
**Status**: APPROVED for Phase 1 Implementation  
**Scope**: CLI-based MVP (FastAPI は Phase 2)

---

## 📌 Executive Summary

Ad-Insight-Spec Phase 1 は、**Meta API への依存を避け**、ダウンロード済み広告素材（動画・画像・テキスト）と LP をローカルで分析して、構造化JSON診断結果を生成します。

**戦略**: ファイル入力 → 各種分析エンジン → LLM ラベリング → JSON生成 → 永続化

**MVP 完成条件**: 
- CLI で `ad-insight-spec analyze --input <file> --lp <url>` を実行 → 5分以内に JSON診断結果を生成
- 3つの入力モード（file_only / file_plus_lp / file_plus_lp_plus_manual_kpi）に対応
- 定性診断（Creative Fatigue、Message Clarity）が 80%精度以上で動作

---

## 1️⃣ なぜ Meta API-First ではなく File-First か？

### Meta API-First のコスト（Phase 2以降に延期）

| 課題 | 影響 |
|------|------|
| **OAuth 認可フロー** | 開発環境構築が複雑、UI の認可画面が必要 |
| **API キー管理** | 秘密鍵の安全な管理、CI/CD パイプライン対応 |
| **Rate Limit 対応** | キューイング、リトライロジック実装が必須 |
| **API バージョン変更** | Meta Graph API のメジャーアップデート対応コスト |
| **許可申請期間** | Meta ビジネスアカウント確認に 1～2週間 |
| **コスト**: MVP 開発が **3～4週間延長** |

### File-First のメリット（Phase 1 採択）

| メリット | 実装効果 |
|---------|--------|
| **ローカル完結** | OAuth / キー管理不要 → CI/CD パイプラインが単純 |
| **即開発開始** | API 許可待ち不要 → GitHub Actions で自動テスト可能 |
| **MVP 高速化** | 2-3週間で CLI MVP を完成 |
| **ユーザー体験向上** | ファイルをドラッグ&ドロップ → 即分析（レイテンシー低） |
| **将来互換性** | File-First パイプラインに Meta API Input Adapter を差し込むだけ |

### 理想状態（Phase 3）

```text
ユーザー
├─ ローカルファイル → File Input Service
├─ Meta API → Meta Adapter
├─ Google Ads API → Google Adapter
└─ TikTok Ads API → TikTok Adapter
       ↓
Ingestion Service（統一インターフェース）
       ↓
分析パイプライン（共通）
```

**結論**: File-First は Meta / Google / TikTok を統一的に扱う設計の第一歩

---

## 2️⃣ Phase 1 の完成条件（Definition of Done）

### MVP としての Checklist

- [ ] **CLI ツール**
  - `ad-insight-spec analyze --input <file_path> --lp <url_or_path> --kpi <json_file>` が動作
  - `--lp` と `--kpi` はオプション
  - JSON 診断結果を stdout / ファイルに出力

- [ ] **3つの入力モード対応**
  - `--mode file_only`: 素材のみ分析
  - `--mode file_plus_lp`: 素材 + LP 分析
  - `--mode file_plus_lp_plus_manual_kpi`: 素材 + LP + KPI 分析

- [ ] **入力ファイル形式対応**
  - 動画: MP4 / MOV（30秒～60秒）
  - 画像: PNG / JPG（複数枚対応）
  - LP: URL / HTML ローカルファイル
  - KPI: JSON （impressions, clicks, spend, conversions）

- [ ] **分析エンジン稼働**
  - [ ] OCR: テキスト検出（画像内のテキスト）
  - [ ] ビデオ フレーム抽出: 動画内の主要フレーム分析
  - [ ] LLM: Creative Fatigue / Message Clarity ラベリング
  - [ ] LP Parse: フォーム項目検出、FV コピー抽出
  - [ ] Message Matching: 広告文 ↔ LP 整合性スコア

- [ ] **出力**
  - JSON 診断結果（v0.2 スキーマ）
  - 定性診断 80%精度以上
  - PostgreSQL への永続化（オプション Phase 1）

- [ ] **テスト**
  - pytest で 3つのモード各 5～10ケース
  - サンプルデータ検証スクリプト合格
  - 処理時間 1ファイル あたり < 5分

---

## 3️⃣ 入力資産の種類と仕様

### 3.1 動画広告（Video）

| 項目 | 仕様 |
|------|------|
| **形式** | MP4, MOV |
| **解像度** | 1080p 推奨（最小 720p） |
| **フレームレート** | 24fps～60fps |
| **長さ** | 15秒～120秒（推奨 30秒） |
| **ファイルサイズ** | < 500MB |
| **抽出内容** | フレーム（5～10枚）, テキストオーバーレイ, 音声トランスクリプト（オプション） |

**処理**:
1. FFmpeg で 5つの均等フレーム抽出（0%, 25%, 50%, 75%, 100%）
2. 各フレームに OCR + Vision API
3. テキストオーバーレイ文字列を統合（primary_text）
4. LLM に画像 → Hook type, Tone, Emotion ラベリング

---

### 3.2 画像広告（Image）

| 項目 | 仕様 |
|------|------|
| **形式** | PNG, JPG, WebP |
| **解像度** | 1080x1080 推奨（方形） |
| **複数枚** | Carousel 対応（最大 5枚） |
| **ファイルサイズ** | 各 < 100MB |
| **抽出内容** | テキストオーバーレイ, 配色分析, 物体検出 |

**処理**:
1. 各画像に OCR
2. Google Vision API で物体検出（detected_objects）
3. 配色分析（dominant_colors）
4. LLM に画像 → Hook type, Tone, Emotion ラベリング

---

### 3.3 フィード投稿（Feed Post）

| 項目 | 仕様 |
|------|------|
| **形式** | テキスト + 画像/動画 |
| **投稿文字数** | < 2000 文字 |
| **キャプション** | コピー分析対象 |
| **ハッシュタグ** | 抽出・記録（オプション） |

**処理**:
1. テキスト抽出 → primary_text
2. 画像/動画の処理は上記に同じ
3. LLM で Hook, Appeal, Pain Point ラベリング

---

### 3.4 投稿文/キャプション（Text Only）

| 項目 | 仕様 |
|------|------|
| **形式** | プレーンテキスト (.txt) / Markdown (.md) |
| **文字数** | < 2000 文字 |
| **言語** | 日本語（多言語対応は Phase 2） |

**処理**:
1. テキスト解析 → primary_text, headline, body_text 抽出
2. LLM で Hook, Appeal, Message Clarity ラベリング
3. format = "text_only" として記録

---

### 3.5 Landing Page (LP)

| 項目 | 仕様 |
|------|------|
| **入力形式** | URL または ローカル HTML ファイル |
| **アクセス方式** | HTTP(S) / ローカルファイル |
| **スクレイピング** | BeautifulSoup（JavaScript 描画不要なページ向け） |
| **タイムアウト** | 10秒 |
| **抽出内容** | FV コピー, Offer, Form fields, CTA ボタン |

**処理**:
1. URL の場合: HTTP GET → HTML 取得
2. ローカルファイルの場合: ファイル読み込み
3. BeautifulSoup で解析：
   - `<h1>`, `<h2>` → fv_headline
   - `<p>` 最初の段落 → fv_copy
   - `<form>` タグ → form_field_count
   - `<button>` CTA テキスト → cta_button_text
4. LLM で Offer 抽出、Message Consistency スコア計算

---

### 3.6 Optional KPI

| 項目 | 仕様 |
|------|------|
| **形式** | JSON ファイル |
| **必須フィールド** | impressions, clicks, spend, conversions |
| **オプション** | reach, frequency, conversion_value, roas |
| **期間** | analysis_period.start, analysis_period.end |

**JSON 例**:
```json
{
  "impressions": 45000,
  "clicks": 1350,
  "spend": 180000,
  "conversions": 45,
  "analysis_period": {
    "start": "2026-06-01",
    "end": "2026-06-22"
  }
}
```
処理:

JSON 解析 → performance セクション に埋め込み
CTR, CVR, CPA を自動計算
定量診断（quantitative diagnostics）を有効化
4️⃣ 処理パイプライン
アーキテクチャ図
```text
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI Entry Point                             │
│  $ ad-insight-spec analyze --input <file> --lp <url> --kpi <json>  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                ┌──────────▼──────────┐
                │  Input Validation   │
                │  - File exists?     │
                │  - Format OK?       │
                │  - Permissions?     │
                └──────────┬──────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
   ┌────▼──────┐                    ┌────────▼───────┐
   │ Ingestion │                    │  LP Ingestion  │
   │  Service  │                    │   Service      │
   └────┬──────┘                    └────────┬───────┘
        │                                    │
   ┌────▼──────────────────────────────────▼────┐
   │   Metadata Extraction Service              │
   │  - asset_id 生成                           │
   │  - File 基本情報（サイズ、解像度）         │
   │  - Duration（動画の場合）                  │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   Content Analysis Service                │
   │  ┌─────────────────┐   ┌──────────────┐  │
   │  │  OCR Service    │   │ Vision API   │  │
   │  │  (Tesseract)    │   │ (Google)     │  │
   │  └─────────────────┘   └──────────────┘  │
   │  ┌─────────────────┐   ┌──────────────┐  │
   │  │ Video Frame     │   │ Color        │  │
   │  │ Extractor       │   │              │  │
   │  │ (FFmpeg)        │   │ Analysis     │  │
   │  └─────────────────┘   └──────────────┘  │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   LP Parse Service                        │
   │  - BeautifulSoup HTML 解析                │
   │  - FV Copy 抽出                           │
   │  - Form fields 検出                       │
   │  - CTA Button 抽出                        │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   LLM Labeling Service                    │
   │  - Hook type (benefit, curiosity, etc)    │
   │  - Tone & Emotion                         │
   │  - Pain Points / Benefits 抽出            │
   │  - Message Consistency Score 計算         │
   │  - Recommended Actions 生成               │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   Converter Service                       │
   │  - input_metadata, asset_meta, creative   │
   │    _core, landing_page を JSON に         │
   │  - Performance 計算（KPI 入力時）         │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   Diagnostics Generation Service          │
   │  - qualitative diagnostics 生成           │
   │  - quantitative diagnostics 生成          │
   │    （KPI 入力時のみ）                     │
   │  - views セクション生成                    │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   Repository / Persistence                │
   │  - PostgreSQL に保存（オプション）        │
   │  - JSON ファイル出力                      │
   └────┬──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────────┐
   │   Output                                  │
   │  - ad_insight_spec.json (stdout)          │
   │  - [Optional] DB record                   │
   │  - Exit code 0 (success) / 1 (error)     │
   └──────────────────────────────────────────┘
```
5️⃣ 各コンポーネントの責務
5.1 Ingestion Service
責務: ファイル入力 → バイナリ / テキストデータ に正規化

メソッド	入力	出力	責務
ingest_video(file_path)	MP4/MOV	IngestedAsset(format, data, metadata)	ビデオファイルを解析、基本メタデータ抽出
ingest_image(file_path)	PNG/JPG	IngestedAsset(format, data, metadata)	画像ファイル読み込み、解像度・色空間情報
ingest_text(file_path)	TXT/MD	IngestedAsset(format, data, metadata)	テキスト読み込み、エンコーディング自動判定
ingest_kpi(file_path)	JSON	KPIData	JSON 解析、バリデーション
エラーハンドリング:

ファイルが存在しない → FileNotFoundError
形式が非対応 → UnsupportedFormatError
ファイル破損 → CorruptedFileError
実装場所: backend/app/services/ingestion_service.py

5.2 Metadata Extraction Service
責務: 各資産から基本メタデータを抽出

メソッド	入力	出力	責務
generate_asset_id(file_path)	str	str	asset_20260622_143000_local_uuid 形式で asset_id 生成
extract_video_metadata(data)	bytes	dict	duration, resolution, fps, codec
extract_image_metadata(data)	bytes	dict	width, height, color_space, dpi
extract_text_metadata(data)	str	dict	char_count, line_count, language
実装場所: backend/app/services/metadata_service.py

5.3 Content Analysis Service
責務: OCR、Vision API、ビデオフレーム抽出、配色分析

5.3.1 OCR Engine (Tesseract)
メソッド	入力	出力	責務
extract_text_from_image(image)	PIL Image	str	画像内のテキストを認識
extract_text_with_confidence(image)	PIL Image	list[dict]	テキスト + 信頼度スコア
実装場所: backend/app/services/ocr_service.py

```python
import pytesseract
from PIL import Image

def extract_text_from_image(image_path: str) -> str:
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang='jpn')
    return text.strip()
```

5.3.2 Vision API (Google Vision)
メソッド	入力	出力	責務
detect_objects(image_path)	str	list[str]	画像内の物体を検出（laptop, person など）
detect_colors(image_path)	str	list[str]	配色を分析（#FF5733 形式）
detect_text(image_path)	str	str	OCR（ローカル Tesseract より精度高い）
実装場所: backend/app/services/vision_service.py

```python
from google.cloud import vision

def detect_objects(image_path: str) -> list[str]:
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(filename=image_path))
    response = client.object_localization(image=image)
    return [obj.name for obj in response.localized_objects]
```

5.3.3 Video Frame Extractor (FFmpeg)
メソッド	入力	出力	責務
extract_key_frames(video_path, num_frames=5)	str	list[PIL Image]	動画から N 個の均等フレーム抽出
get_video_duration(video_path)	str	float	動画の長さを秒単位で取得
実装場所: backend/app/services/video_service.py

```python
import subprocess
import os

def extract_key_frames(video_path: str, num_frames: int = 5) -> list[str]:
    """動画から 5 つの均等フレームを抽出"""
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f'select=eq(n\\,0)+eq(n\\,{num_frames-1})+gte(t\\,1)+gte(t\\,2)',
        '-vsync', '0',
        f'/tmp/frame_%03d.png'
    ]
    subprocess.run(cmd, check=True)
    return sorted([f'/tmp/frame_{i:03d}.png' for i in range(num_frames)])
```

5.4 LP Parse Service
責務: LP の HTML 解析、FV コピー・フォーム・CTA 抽出

メソッド	入力	出力	責務
fetch_lp(url_or_path)	str	str	LP の HTML を取得
extract_fv_copy(html)	str	str	FV のメイン訴求コピー抽出
extract_form_fields(html)	str	list[str]	フォームの項目名リスト
extract_cta_text(html)	str	str	CTA ボタンのテキスト
extract_offer(html)	str	str	オファー内容（「30日無料」等）を抽出
実装場所: backend/app/services/lp_service.py

```python
from bs4 import BeautifulSoup
import requests

def fetch_lp(url_or_path: str) -> str:
    """URL または ローカルファイルから HTML を取得"""
    if url_or_path.startswith('http'):
        response = requests.get(url_or_path, timeout=10)
        return response.text
    else:
        with open(url_or_path, 'r', encoding='utf-8') as f:
            return f.read()

def extract_fv_copy(html: str) -> str:
    """FV のメイン訴求を抽出"""
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    if h1:
        return h1.get_text().strip()
    h2 = soup.find('h2')
    if h2:
        return h2.get_text().strip()
    return ""

def extract_form_fields(html: str) -> list[str]:
    """フォーム項目を抽出"""
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.find('form')
    if not form:
        return []
    inputs = form.find_all(['input', 'textarea', 'select'])
    return [inp.get('name', inp.get('placeholder', '')) for inp in inputs]
```

5.5 LLM Labeling Service
責務: LLM（Gemini / GPT-4o）に画像 + テキストを送信、Hook / Tone / Emotion ラベリング

メソッド	入力	出力	責務
analyze_creative(image_paths, primary_text, headline)	list[str], str, str	dict	Hook type, Tone, Emotion, Pain Points, Benefits
calculate_message_consistency(ad_text, lp_copy)	str, str	float, str	整合性スコア + 根拠文
generate_recommendations(diagnostics)	dict	list[str]	LLM が改善案を生成
実装場所: backend/app/services/llm_service.py

```python
from google.generativeai import GenerativeModel
import base64

def analyze_creative(
    image_paths: list[str],
    primary_text: str,
    headline: str
) -> dict:
    """LLM に画像 + テキストを送信、ラベリング"""
    model = GenerativeModel('gemini-2.0-flash')
    
    # 画像を base64 エンコード
    image_data = []
    for img_path in image_paths:
        with open(img_path, 'rb') as f:
            encoded = base64.b64encode(f.read()).decode()
            image_data.append({
                'inline_data': {'mime_type': 'image/png', 'data': encoded}
            })
    
    prompt = f"""
    このクリエイティブを分析してください：
    - 見出し: {headline}
    - テキスト: {primary_text}
    
    以下をJSON形式で返してください:
    {{
      "hook_type": "benefit" | "curiosity" | "pain_point" | "social_proof" | "scarcity",
      "primary_tone": "professional" | "casual" | "humorous" | "urgent" | "inspirational",
      "detected_emotions": ["excitement", "trust", "urgency"],
      "identified_pain_points": ["time_consuming", "expensive"],
      "identified_benefits": ["saves_time", "cost_effective"],
      "target_audience_inferred": "description"
    }}
    """
    
    response = model.generate_content([*image_data, prompt])
    import json
    return json.loads(response.text)

def calculate_message_consistency(ad_text: str, lp_copy: str) -> tuple[float, str]:
    """広告文とLP FVコピーの整合性を計算"""
    model = GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""
    広告文とLPコピーの整合性を分析してください:
    
    【広告文】
    {ad_text}
    
    【LP FVコピー】
    {lp_copy}
    
    JSON形式で返してください:
    {{
      "match_score": 0.92,
      "consistency_basis": "理由を日本語で記述",
      "key_alignment_points": ["一致点1", "一致点2"],
      "mismatch_areas": []
    }}
    """
    
    response = model.generate_content(prompt)
    import json
    data = json.loads(response.text)
    return data['match_score'], data['consistency_basis']
```

5.6 Converter Service
責務: 各種分析結果を ad_insight_spec v0.2 JSON フォーマットに統合

メソッド	入力	出力	責務
convert_to_ad_insight_spec(analysis_result, mode)	dict	dict	分析結果を v0.2 スキーマに準拠した JSON に変換
populate_input_metadata(mode, file_paths)	str, dict	dict	input_metadata セクション生成
populate_asset_meta(metadata)	dict	dict	asset_meta セクション生成
populate_creative_core(analysis)	dict	dict	creative_core セクション生成
populate_landing_page(lp_analysis)	dict	dict	landing_page セクション生成
populate_performance(kpi)	dict	dict	performance セクション生成（KPI 入力時のみ）
実装場所: backend/app/services/converter_service.py

5.7 Diagnostics Generation Service
責務: 分析結果から定性 / 定量診断を生成

5.7.1 Qualitative Diagnostics（常に実施）
メソッド	入力	出力	責務
assess_creative_fatigue(llm_labels, visual_analysis)	dict	dict	Fatigue Risk レベル + 根拠
assess_message_clarity(text_analysis)	dict	dict	Clarity Score + 説明
assess_lp_consistency(ad_text, lp_copy)	str, str	dict	Match Risk + 根拠（LP 入力時）
assess_form_usability(form_fields, scroll_depth)	dict	dict	Form Difficulty 評価
generate_creative_improvements(diagnostics)	dict	list[str]	LLM による改善案
実装場所: backend/app/services/diagnostics_service.py

5.7.2 Quantitative Diagnostics（KPI 入力時のみ）
メソッド	入力	出力	責務
assess_performance_status(kpi)	dict	str	excellent / good / fair / poor の判定
compare_to_benchmark(metric_name, value)	str, float	str	業界ベンチマークとの比較
generate_optimizations(performance_status)	dict	list[str]	KPI 基づく改善提案
5.8 Repository Service
責務: ad_insight_spec の永続化（ファイル / DB）

メソッド	入力	出力	責務
save_to_json(spec, output_path)	dict, str	None	JSON ファイルに保存
save_to_db(spec)	dict	int	PostgreSQL に保存、record ID 返却
load_from_db(asset_id)	str	dict	asset_id で記録を検索
実装場所: backend/app/repositories/ad_insight_repository.py

6️⃣ CLI と FastAPI の役割分担
MVP（Phase 1）: CLI-First
```bash
$ ad-insight-spec analyze \
    --input /path/to/video.mp4 \
    --lp https://example.com/lp \
    --kpi /path/to/kpi.json \
    --mode file_plus_lp_plus_manual_kpi \
    --output result.json
```
実装場所: backend/app/cli/main.py（Click / Typer フレームワーク）

責務:

引数解析
Ingestion Service 呼び出し
各 Service を順序立てて実行
結果を JSON ファイル / stdout に出力
Exit code 返却
参考実装:

```python
import click
from app.services import IngestionService, MetadataService, ConverterService

@click.command()
@click.option('--input', required=True, help='Input file path')
@click.option('--lp', required=False, help='LP URL or file path')
@click.option('--kpi', required=False, help='KPI JSON file path')
@click.option('--mode', default='file_plus_lp_plus_manual_kpi')
@click.option('--output', default='result.json')
def analyze(input, lp, kpi, mode, output):
    """Analyze ad creative and generate diagnostic spec"""
    try:
        ingestion_svc = IngestionService()
        asset = ingestion_svc.ingest(input)
        
        metadata_svc = MetadataService()
        metadata = metadata_svc.extract(asset)
        
        # ... 各 Service 実行
        
        converter_svc = ConverterService()
        spec = converter_svc.convert_to_ad_insight_spec(analysis, mode)
        
        # 出力
        with open(output, 'w') as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)
        
        click.echo(f"✅ Generated: {output}")
        return 0
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        return 1

if __name__ == '__main__':
    analyze()
```

Phase 2: FastAPI エンドポイント追加（Web UI 対応）
```http
POST /api/v1/analyze
Content-Type: multipart/form-data

{
  "file": <video/image file>,
  "lp_url": "https://example.com/lp",
  "kpi": <optional JSON>,
  "mode": "file_plus_lp_plus_manual_kpi"
}

Response:
{
  "asset_id": "asset_20260622_143000_local_a1b2c3",
  "spec": { ... ad_insight_spec v0.2 ... },
  "processing_time_ms": 3200,
  "status": "success"
}
```
実装場所: backend/app/api/v1/analyze.py（FastAPI router）

CLI と FastAPI の共通化:

```python
# CLI と API の共通ロジック
class AnalysisOrchestrator:
    def run_analysis(self, input_path, lp, kpi, mode) -> dict:
        # 実装は共通
        ...

# CLI から呼び出し
orchestrator = AnalysisOrchestrator()
spec = orchestrator.run_analysis(...)

# FastAPI エンドポイントから呼び出し
@app.post("/api/v1/analyze")
def analyze_endpoint(file: UploadFile, lp: str = None, ...):
    orchestrator = AnalysisOrchestrator()
    spec = orchestrator.run_analysis(...)
```
7️⃣ 将来の Meta / Google / TikTok Adapter の差し込み位置
Adapter Pattern（Phase 2/3）
現在の構造を Input Abstraction にすることで、API 連携を後付け可能に：

```python
# 現在（Phase 1）: File Input
from app.services import IngestionService

class FileIngestionService(IngestionService):
    def ingest(self, file_path: str) -> IngestedAsset:
        # ファイル読み込み
        ...

# 将来（Phase 2）: Meta API Input
class MetaAdapterService(IngestionService):
    def ingest(self, ad_id: str, api_token: str) -> IngestedAsset:
        # Meta API から ad_id で広告を取得
        response = self.meta_api.get_ad(ad_id, fields=['creative', 'insights'])
        return IngestedAsset(
            format='video' if response.is_video else 'image',
            data=response.creative_data,
            metadata={...}
        )

# 利用側は同じインターフェース
def analyze(input_spec: InputSpec):
    if input_spec.source == 'file':
        ingestion = FileIngestionService()
    elif input_spec.source == 'meta':
        ingestion = MetaAdapterService()
    elif input_spec.source == 'google':
        ingestion = GoogleAdapterService()
    
    asset = ingestion.ingest(input_spec.input)
    # 以降の処理は同じ
```

パイプラインの統一化
```text
Meta Adapter ──┐
               ├─→ Ingestion (抽象) ──→ Content Analysis ──→ LLM ──→ Diagnostics
Google Adapter ┤                                 ↑
               │                            共通パイプライン
TikTok Adapter ├─→ Ingestion (抽象)
               │
File Input ────┘
```
実装場所: backend/app/services/adapters/

file_adapter.py
meta_adapter.py（Phase 2）
google_adapter.py（Phase 2）
tiktok_adapter.py（Phase 3）
8️⃣ リスク と未決定事項
技術的リスク
リスク	対策	Phase
LLM のハルシネーション	サンプルデータで精度測定（80%目標）、定量指標で補強	1
OCR の精度（日本語）	Tesseract + Google Vision のハイブリッド、フォールバック	1
ビデオ処理の遅延	FFmpeg フレーム抽出は 5 フレームのみ、キャッシング機構	1
LP スクレイピングの脆弱性	ローカル HTML ファイル優先、URL は optional	1
メモリ不足（大容量ビデオ）	ストリーミング処理、フレーム抽出後に削除	2
PostgreSQL スキーマ変更	Alembic マイグレーション, v0.1 → v0.2 コンバータ	2
未決定事項
項目	決定内容	優先度	Phase
ビデオフレーム数	5 フレーム（0%, 25%, 50%, 75%, 100%）	高	1
OCR 言語	日本語 lang='jpn' (Tesseract 3.x)	高	1
LLM モデル選択	Gemini 2.0 Flash（コスト・速度重視）	中	1
Benchmark データ	業界平均 CTR 1.5%, CVR 2.5% 等（SaaS 向け初期値）	中	1
LP スクレイピング JavaScript	BeautifulSoup のみ（JS 描画不要）、Selenium は Phase 2	中	1
PostgreSQL 版リリース時期	Phase 1b（初版 CLI リリース後 2 週間）	低	1b
認証機構	Phase 2（Web UI 時に OAuth2）	低	2
9️⃣ 実装優先順位
Phase 1a: Core Pipeline（2週間）
ゴール: CLI MVP で file_plus_lp_plus_manual_kpi が動作

実装順序:

Week 1

 Ingestion Service（ファイル読み込み）
 Metadata Service（asset_id 生成）
 Video Service（FFmpeg フレーム抽出）
 OCR Service（Tesseract）
 LP Service（BeautifulSoup）
 テスト: サンプルデータ 3 種
Week 2

 LLM Service（Gemini 2.0 Flash）
 Converter Service（JSON 生成）
 Diagnostics Service（定性診断）
 CLI エンドポイント（Click）
 E2E テスト: ad-insight-spec analyze --input ... で結果生成確認
Phase 1b: Repository & Diagnostics（1週間、Optional）
ゴール: DB 永続化、定量診断対応

 Repository Service（PostgreSQL）
 Diagnostics Quantitative（KPI 分析）
 Benchmark Database（業界平均値）
 テスト: KPI 入力時の定量診断検証
Phase 2: Web UI (3週間、別トラック)
 FastAPI: /api/v1/analyze エンドポイント
 Vue.js フロントエンド
 ファイルアップロード UI
 結果表示ダッシュボード
🔟 MVP と将来拡張の境界
MVP（Phase 1a）に含まれる
✅ CLI ツール
✅ ファイル入力（動画・画像・テキスト）
✅ LP URL / HTML 入力
✅ LLM ラベリング（Creative Fatigue, Message Clarity）
✅ JSON 診断結果出力
✅ 定性診断（qualitative diagnostics）
✅ 3つの入力モード（file_only, file_plus_lp, file_plus_lp_plus_manual_kpi）
MVP に含まれない（Phase 2/3 へ）
❌ PostgreSQL 永続化（Phase 1b）
❌ Web UI（FastAPI + Vue.js）（Phase 2）
❌ Meta Ads API 連携（Phase 2）
❌ Google Ads API 連携（Phase 3）
❌ TikTok Ads API 連携（Phase 3）
❌ ユーザー認証（Phase 2）
❌ マルチテナント化（Phase 3）
❌ Alembic マイグレーション（Phase 1b）
境界を守るための チェックリスト
 新機能を追加する前に「これは MVP に必須か?」を問う
 API 連携は Phase 2 以降へ延期することを原則とする
 入力ファイルのバリデーションは厳密に、出力 JSON は v0.2 に完全準拠
 テストは CLI 単位で（FastAPI テストは Phase 2）
📁 ディレクトリ構造（Phase 1 対応版）
```text
backend/
├── app/
│   ├── cli/
│   │   └── main.py                 ← CLI entry point
│   ├── services/
│   │   ├── ingestion_service.py
│   │   ├── metadata_service.py
│   │   ├── ocr_service.py
│   │   ├── vision_service.py       ← Google Vision API
│   │   ├── video_service.py        ← FFmpeg
│   │   ├── lp_service.py
│   │   ├── llm_service.py          ← Gemini 2.0 Flash
│   │   ├── converter_service.py
│   │   ├── diagnostics_service.py
│   │   └── adapters/
│   │       ├── base_adapter.py
│   │       ├── file_adapter.py
│   │       ├── meta_adapter.py     ← Phase 2
│   │       ├── google_adapter.py   ← Phase 3
│   │       └── tiktok_adapter.py   ← Phase 3
│   ├── repositories/
│   │   └── ad_insight_repository.py
│   ├── core/
│   │   ├── config.py
│   │   └── constants.py            ← 業界ベンチマーク定義
│   ├── models/
│   │   └── ad_insight.py
│   ├── schemas/
│   │   └── ad_insight.py           ← Pydantic v0.2
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   └── api/                         ← Phase 2
│       └── v1/
│           └── analyze.py
├── tests/
│   ├── test_ingestion_service.py
│   ├── test_ocr_service.py
│   ├── test_video_service.py
│   ├── test_lp_service.py
│   ├── test_llm_service.py
│   ├── test_converter_service.py
│   ├── test_diagnostics_service.py
│   └── test_cli.py
├── scripts/
│   └── validate_sample_data.py
└── requirements.txt
```
🎬 実装開始前のチェックリスト
 Pydantic v0.2 スキーマ確定（済み）
 サンプルデータ 3 種作成（次ステップ）
 技術選定確定：
 LLM: Gemini 2.0 Flash
 OCR: Tesseract (+ Google Vision API)
 Video: FFmpeg
 LP Parse: BeautifulSoup
 Framework: Click (CLI)
 各 Service の責務定義（このドキュメント）
 テスト戦略定義
 GitHub Issues / Tasks 作成
 CI/CD パイプライン設定
最終更新: 2026-06-23
ステータス: READY FOR IMPLEMENTATION
次ステップ: サンプルデータ作成 → Pydantic v0.2 実装 → Service 実装開始
