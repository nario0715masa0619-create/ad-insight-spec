import os
import json
import re
from typing import Optional, Literal
from dotenv import load_dotenv
import openai
import google.generativeai as genai
from pydantic import ValidationError

from app.schemas.llm_response import LLMResponseSchema, CreativeCoreSchema

# .env から API キーを読み込む
env_path = r"C:\Users\nario\.ad-insight-spec\.env"
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class LLMService:
    """GPT-4o（本命）と Gemini 2.0 Flash（比較対象）のデュアル実装"""
    
    GPT_MODEL = "gpt-4o"
    GEMINI_MODEL = "gemini-2.0-flash"
    MAX_RETRIES = 3
    
    # 共通プロンプト（JSON Schema 固定）
    ANALYSIS_PROMPT_TEMPLATE = """
あなたは広告クリエイティブ分析の専門家です。以下の情報を分析して、指定の JSON フォーマットで返してください。

【画像情報】
{image_description}

【ランディングページコンテンツ】
{lp_content}

【必須フォーマット（厳密に従うこと）】
{{
    "visuals": {{
        "dominant_colors": ["色1", "色2", ...],
        "composition": "構図の説明（5文字以上）",
        "style": "スタイル名（3文字以上）",
        "clarity": "高または中または低"
    }},
    "tone": {{
        "primary_tone": ["トーン1", "トーン2", ...],
        "emotional_appeal": "論理的または感情的または混合",
        "call_to_action": "強または中または弱"
    }},
    "ai_labels": ["ラベル1", "ラベル2", ...（1〜15個）]
}}

【重要】
- 必ず上記フォーマットの JSON のみを返してください
- 他の説明文や前置きは絶対に含めないこと
- JSON が無効な場合は、修正版のみ返してください
- すべてのフィールドは必須です（省略不可）
"""
    
    @staticmethod
    def _validate_and_parse_response(response_text: str) -> dict:
        """
        LLM レスポンスを JSON として解析し、Schema で検証
        
        Args:
            response_text: LLM からの生テキスト
        
        Returns:
            検証済みの dict
        
        Raises:
            ValueError: JSON 解析またはスキーマ検証失敗
        """
        # JSON ブロック（```json ... ```）を抽出
        json_text = response_text.strip()
        if "```json" in json_text:
            json_start = json_text.find("```json") + 7
            json_end = json_text.find("```", json_start)
            if json_end > json_start:
                json_text = json_text[json_start:json_end].strip()
        elif "```" in json_text:
            json_start = json_text.find("```") + 3
            json_end = json_text.find("```", json_start)
            if json_end > json_start:
                json_text = json_text[json_start:json_end].strip()
        
        # JSON 解析
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}")
        
        # Schema 検証
        try:
            creative_core = CreativeCoreSchema(**data)
            return creative_core.model_dump()
        except ValidationError as e:
            raise ValueError(f"Schema validation failed: {str(e)}")
    
    @staticmethod
    def analyze_creative_gpt(
        image_description: Optional[str] = None,
        lp_content: Optional[str] = None
    ) -> LLMResponseSchema:
        """
        GPT-4o で CreativeCore を分析（自動再試行付き）
        
        Args:
            image_description: 画像の説明文
            lp_content: LP のテキストコンテンツ
        
        Returns:
            LLMResponseSchema
        """
        if not OPENAI_API_KEY:
            return LLMResponseSchema(
                success=False,
                model=LLMService.GPT_MODEL,
                creative_core=None,
                error_details="OPENAI_API_KEY is not set in environment variables"
            )
        
        prompt = LLMService.ANALYSIS_PROMPT_TEMPLATE.format(
            image_description=image_description or "なし",
            lp_content=lp_content or "なし"
        )
        
        for attempt in range(LLMService.MAX_RETRIES):
            try:
                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model=LLMService.GPT_MODEL,
                    messages=[
                        {"role": "system", "content": "You are an expert ad creative analyst. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )
                
                response_text = response.choices[0].message.content
                creative_core = LLMService._validate_and_parse_response(response_text)
                
                return LLMResponseSchema(
                    success=True,
                    model=LLMService.GPT_MODEL,
                    creative_core=creative_core,
                    retry_count=attempt
                )
                
            except (ValueError, Exception) as e:
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMResponseSchema(
                        success=False,
                        model=LLMService.GPT_MODEL,
                        creative_core=None,
                        retry_count=attempt,
                        error_details=f"Failed after {LLMService.MAX_RETRIES} retries: {str(e)}"
                    )
    
    @staticmethod
    def analyze_creative_gemini(
        image_description: Optional[str] = None,
        lp_content: Optional[str] = None
    ) -> LLMResponseSchema:
        """
        Gemini 2.0 Flash で CreativeCore を分析（自動再試行付き）
        
        Args:
            image_description: 画像の説明文
            lp_content: LP のテキストコンテンツ
        
        Returns:
            LLMResponseSchema
        """
        if not GEMINI_API_KEY:
            return LLMResponseSchema(
                success=False,
                model=LLMService.GEMINI_MODEL,
                creative_core=None,
                error_details="GEMINI_API_KEY is not set in environment variables"
            )
        
        prompt = LLMService.ANALYSIS_PROMPT_TEMPLATE.format(
            image_description=image_description or "なし",
            lp_content=lp_content or "なし"
        )
        
        for attempt in range(LLMService.MAX_RETRIES):
            try:
                model = genai.GenerativeModel(LLMService.GEMINI_MODEL)
                response = model.generate_content(prompt)
                
                response_text = response.text
                creative_core = LLMService._validate_and_parse_response(response_text)
                
                return LLMResponseSchema(
                    success=True,
                    model=LLMService.GEMINI_MODEL,
                    creative_core=creative_core,
                    retry_count=attempt
                )
                
            except (ValueError, Exception) as e:
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMResponseSchema(
                        success=False,
                        model=LLMService.GEMINI_MODEL,
                        creative_core=None,
                        retry_count=attempt,
                        error_details=f"Failed after {LLMService.MAX_RETRIES} retries: {str(e)}"
                    )
    
    @staticmethod
    def analyze_creative(
        image_description: Optional[str] = None,
        lp_content: Optional[str] = None,
        model: Literal["gpt", "gemini"] = "gpt"
    ) -> LLMResponseSchema:
        """
        CreativeCore を分析（GPT または Gemini を選択）
        
        Args:
            image_description: 画像の説明文
            lp_content: LP のテキストコンテンツ
            model: 使用するモデル（"gpt" または "gemini"）
        
        Returns:
            LLMResponseSchema
        """
        if model == "gpt":
            return LLMService.analyze_creative_gpt(image_description, lp_content)
        elif model == "gemini":
            return LLMService.analyze_creative_gemini(image_description, lp_content)
        else:
            raise ValueError(f"Unknown model: {model}")
