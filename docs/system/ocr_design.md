# OCRService 設計仕様

## フレーム抽出ポリシー

### 動画フレーム抽出対象
- **先頭フレーム** (0.0 = relative position 0%)
- **中盤フレーム** (0.5 = relative position 50%)
- **末尾フレーム** (1.0 = relative position 100%)

理由: 広告動画では冒頭と終盤に重要なテキスト（CTA、ブランド名）が配置されることが多い。中盤は変動要素をキャッチ。

### OCR 結果マージ方針
1. 各フレームの OCR テキストを個別に抽出
2. テキストを改行で連結
3. 重複テキスト（同一行）は 1 回だけ保持

例:
Frame 0: "SALE 50% OFF" 
Frame 1: "50% OFF Limited Time" 
Frame 2: "SALE 50% OFF Call Now"

→ Merged: "SALE 50% OFF\nLimited Time\nCall Now"

## 失敗時の Fail-Soft 仕様

OCR 処理失敗時も以下の構造化空結果を返却（アプリケーション継続稼働）:

```json
{
    "success": false,
    "ocr_extracted_text": "",
    "confidence": 0.0,
    "raw_data": null
}
```

LLM への入力時も ocr_extracted_text が空文字列で渡される（LLM が回復分析を試みる）。

## 言語設定
Tesseract の言語パラメータ: 'eng+jpn' （英語と日本語の混在広告に対応）
