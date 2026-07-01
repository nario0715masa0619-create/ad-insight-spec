import os
import json
import re
from typing import Optional, Literal
from dotenv import load_dotenv
import httpx
import openai
import google.generativeai as genai
from pydantic.v1 import ValidationError
from typing import Union
import logging

from app.schemas.llm_response import LLMResponseSchema, CreativeCoreSchema, ImprovementCommentsSchema, LLMImprovementValidationError
from app.services.llm_validator_service import LLMValidatorService

logger = logging.getLogger(__name__)

# .env から API キーを読み込む
env_paths = [
    r"C:\Users\nario\.ad-insight-spec\.env",
    "/home/nario_o_0715_masa_0619/.ad-insight-spec/.env",
    "/root/.ad-insight-spec/.env",
    ".env"
]
for path in env_paths:
    if os.path.exists(path):
        load_dotenv(dotenv_path=path)
        break
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
            # Pydantic v2 互換のメソッドがあるかチェック
            if hasattr(CreativeCoreSchema, "model_validate"):
                creative_core = CreativeCoreSchema.model_validate(data)
            else:
                creative_core = CreativeCoreSchema(**data)
                
            if hasattr(creative_core, "model_dump"):
                return creative_core.model_dump()
            else:
                return creative_core.dict()
        except Exception as e:
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
                proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
                http_client = httpx.Client(proxy=proxy_url) if proxy_url else None
                client = openai.OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
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

    IMPROVEMENT_ANALYSIS_PROMPT = """
あなたは広告クリエイティブ分析の専門家です。
以下の情報に基づいて、構造化された改善コメントを JSON 形式で返してください。

【分析対象情報】
{analysis_data}

【必須ルール - 以下を必ず守ってください】
1. 抽象語だけで終わらない（「改善余地」「訴求力」「魅力」等の曖昧語は使用禁止）
2. 対象箇所を必ず明記する（例：「CTA ボタンテキスト」「見出しの色」）
3. 根拠を必ず付ける（なぜそう判断したか、データや観察に基づく）
4. 推奨アクションを必ず具体化する（「改善する」ではなく「『今すぐ申し込む』に変更」）
5. 同一対象に対する相反評価を出さない（明確/不明確、強い/弱いの両方を言わない）
6. 1 コメント 1 論点にする（複数の問題を 1 つの改善コメントに混ぜない）
7. 日本語は短く明快にする（各文は 30 文字以内を目安）

【JSON 出力フォーマット（必須）】
{{
    "comments": [
        {{
            "issue_summary": "問題を 1 行で説明（20～30 文字）",
            "target_scope": "対象箇所の具体的な部位",
            "evidence": "改善根拠（データ、観察、理由）",
            "recommended_action": "実行可能な具体的アクション",
            "priority": "P0",
            "expected_impact": "改善により期待される効果",
            "confidence": 0.8
        }}
    ],
    "total_count": 1,
    "summary": "全体的な改善方針の簡潔なサマリー"
}}

【出力注意】
- JSON 以外の説明文は一切含めない
- コメントが 0 件の場合も JSON 構造は保持する（"comments": []）
- 各フィールドの文字数を厳守する
"""

    @staticmethod
    def analyze_creative_improvements(
        creative_analysis: dict,
        model: str = "gpt"
    ) -> Union[ImprovementCommentsSchema, LLMImprovementValidationError]:
        """
        LLM で改善コメントを生成（再試行・バリデーション対応）
        """
        if not OPENAI_API_KEY and model == "gpt":
            return LLMImprovementValidationError(
                success=False,
                error_code="API_KEY_MISSING",
                reason="OPENAI_API_KEY is not configured"
            )
        
        # プロンプト作成
        analysis_json = json.dumps(creative_analysis, ensure_ascii=False, indent=2)
        prompt = LLMService.IMPROVEMENT_ANALYSIS_PROMPT.format(analysis_data=analysis_json)
        
        # 再試行ループ（最大 3 回）
        for attempt in range(LLMService.MAX_RETRIES):
            try:
                # LLM 呼び出し
                if model == "gpt":
                    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
                    http_client = httpx.Client(proxy=proxy_url) if proxy_url else None
                    client = openai.OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
                    response = client.chat.completions.create(
                        model=LLMService.GPT_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert ad creative analyzer. Return only valid JSON."
                            },
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=2000
                    )
                    response_text = response.choices[0].message.content
                else:  # gemini
                    model_obj = genai.GenerativeModel(LLMService.GEMINI_MODEL)
                    response = model_obj.generate_content(prompt)
                    response_text = response.text
                
                # JSON 抽出
                json_text = response_text.strip()
                if "```json" in json_text:
                    json_start = json_text.find("```json") + 7
                    json_end = json_text.find("```", json_start)
                    json_text = json_text[json_start:json_end].strip()
                elif "```" in json_text:
                    json_start = json_text.find("```") + 3
                    json_end = json_text.find("```", json_start)
                    json_text = json_text[json_start:json_end].strip()
                
                data = json.loads(json_text)
                
                # バリデーション
                validator = LLMValidatorService()
                improvements = validator.validate_improvement_comments(data)
                
                if isinstance(improvements, ImprovementCommentsSchema):
                    logger.info(f"Improvement comments generated successfully (attempt {attempt + 1})")
                    return improvements
                else:
                    # バリデーション失敗 → 再試行
                    logger.warning(f"Validation failed (attempt {attempt + 1}): {improvements.reason}")
                    if attempt < LLMService.MAX_RETRIES - 1:
                        continue
                    else:
                        return improvements  # 最後の試行で失敗 → エラー返却
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error (attempt {attempt + 1}): {str(e)}")
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMImprovementValidationError(
                        success=False,
                        error_code="JSON_PARSE_ERROR",
                        reason=f"Failed to parse LLM response as JSON: {str(e)}"
                    )
            
            except Exception as e:
                logger.error(f"LLM error (attempt {attempt + 1}): {str(e)}")
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMImprovementValidationError(
                        success=False,
                        error_code="LLM_ERROR",
                        reason=f"LLM generation failed: {str(e)}"
                    )
        
        # すべての試行失敗
        return LLMImprovementValidationError(
            success=False,
            error_code="MAX_RETRIES_EXCEEDED",
            reason=f"Failed to generate valid improvement comments after {LLMService.MAX_RETRIES} attempts"
        )
