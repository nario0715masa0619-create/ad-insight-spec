import os
import json
from typing import Optional
import google.generativeai as genai
from dotenv import load_dotenv

# .env から GEMINI_API_KEY を読み込む
env_path = r"C:\Users\nario\.ad-insight-spec\.env"
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class LLMService:
    """Gemini 2.0 Flash を使用した LLM 分析サービス"""
    
    MODEL_NAME = "gemini-2.0-flash"
    
    @staticmethod
    def analyze_creative(
        file_path: Optional[str] = None,
        image_description: Optional[str] = None,
        lp_content: Optional[str] = None
    ) -> dict:
        """
        CreativeCore 分析を Gemini 2.0 Flash で実行
        
        Args:
            file_path: メディアファイルパス（未使用、互換性維持）
            image_description: 画像の説明文
            lp_content: LP のテキストコンテンツ
        
        Returns:
            {
                "visuals": {...},
                "tone": {...},
                "ai_labels": [...]
            }
        """
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment variables")
        
        # プロンプト構築
        prompt = f"""
あなたは広告クリエイティブ分析の専門家です。以下の情報を分析して、JSON形式で結果を返してください。

【画像情報】
{image_description if image_description else 'なし'}

【ランディングページコンテンツ】
{lp_content if lp_content else 'なし'}

【分析項目】

1. **visuals** (画像・映像の視覚的特性):
   - dominant_colors: [主要色]
   - composition: 構図の説明
   - style: デザインスタイル（モダン、クラシック等）
   - clarity: 視認性（高/中/低）

2. **tone** (トーン・メッセージング):
   - primary_tone: 主要なトーン（楽観的、真摯、ユーモア、緊急性等）
   - emotional_appeal: 感情的訴求（論理的/感情的）
   - call_to_action: CTA の強度（強/中/弱）

3. **ai_labels** (AI が認識したキーワードラベル):
   - Array of strings (最大10個)

【レスポンス形式】必ず以下のJSON形式で返してください。他の説明文は不要です。
{{
    "visuals": {{
        "dominant_colors": ["色1", "色2"],
        "composition": "説明",
        "style": "スタイル",
        "clarity": "高"
    }},
    "tone": {{
        "primary_tone": ["トーン1", "トーン2"],
        "emotional_appeal": "感情的",
        "call_to_action": "強"
    }},
    "ai_labels": ["ラベル1", "ラベル2", "ラベル3"]
}}
"""
        
        try:
            model = genai.GenerativeModel(LLMService.MODEL_NAME)
            response = model.generate_content(prompt)
            
            # レスポンステキストから JSON を抽出
            response_text = response.text.strip()
            
            # JSON ブロック（```json ... ```）を処理
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            result = json.loads(response_text)
            
            # スキーマバリデーション
            if not isinstance(result.get("visuals"), dict):
                result["visuals"] = {}
            if not isinstance(result.get("tone"), dict):
                result["tone"] = {}
            if not isinstance(result.get("ai_labels"), list):
                result["ai_labels"] = []
            
            return result
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {str(e)}")
    
    @staticmethod
    def check_api_availability() -> bool:
        """API キーが利用可能かチェック"""
        return bool(GEMINI_API_KEY)
