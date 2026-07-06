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

from app.schemas.llm_response import (
    LLMResponseSchema,
    CreativeCoreSchema,
    ImprovementCommentsSchema,
    LLMImprovementValidationError,
    DecisionSupport,
    LLMDecisionSupportValidationError,
)
from app.services.llm_validator_service import LLMValidatorService

logger = logging.getLogger(__name__)
# config.py から動的に読み込むため、トップレベルでの API キー初期化を削除
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
        from app.config import get_settings
        settings = get_settings()
        openai_api_key = settings.OPENAI_API_KEY
        if not openai_api_key:
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
                client = openai.OpenAI(api_key=openai_api_key, http_client=http_client)
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
        from app.config import get_settings
        settings = get_settings()
        gemini_api_key = settings.GEMINI_API_KEY
        if not gemini_api_key:
            return LLMResponseSchema(
                success=False,
                model=LLMService.GEMINI_MODEL,
                creative_core=None,
                error_details="GEMINI_API_KEY is not set in environment variables"
            )
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        
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
        from app.config import get_settings
        settings = get_settings()
        openai_api_key = settings.OPENAI_API_KEY
        if not openai_api_key and model == "gpt":
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
                    client = openai.OpenAI(api_key=openai_api_key, http_client=http_client)
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

    # ===== 意思決定支援（decision_support: 強み・弱み・改善提案）生成 =====

    DECISION_SUPPORT_PROMPT = """
あなたは広告クリエイティブの意思決定支援を行う専門家です。
以下のクリエイティブ分析結果をもとに、広告運用の専門家とは限らない担当者が
「配信を続けるか改修するか」「次に何から着手するか」を5秒で判断できるよう、
強み・弱み・改善提案を JSON 形式で構造化してください。

【分析対象情報（CreativeCore）】
{analysis_data}

【評価観点（strengths/weaknesses を検討する際、必ずこれらの観点で分析データを見ること）】
- 訴求軸: メッセージの核は何か。誰の何の悩み/欲求に刺さる設計か
- 視線誘導: 視線が集まりやすい要素（色・サイズ・配置）から情報がどの順で伝わるか
- CTA: 強さ・視認性・行動喚起の具体性（次に何をすればいいか一目で分かるか）
- 可読性: テキスト量・コントラスト・フォントサイズ感が情報を読み取れる設計か
- 差別化: 競合の一般的な訴求と比べて何が独自か、埋もれていないか
- 信頼性: 具体的な数字・社会的証明・権威性等、信じるに足る根拠が示されているか
strengths/weaknesses の title・description は、上記観点のうちどれに関するものかが
読み手に伝わる書き方にすること（観点名をそのままラベルのように書く必要はないが、
「視線が集まる要素が無くCTAまで気づかれにくい」のように観点が滲む具体表現にする）。

【必須ルール】
1. strengths（強み）は「今後も維持・再利用すべき勝ち要素」として書く。単なる褒め言葉（「良い」「魅力的」等）は禁止。何がどう良いか、なぜ維持すべきかを具体的に書く。
2. weaknesses（弱み）は成果の足を引っ張っているボトルネックとして書く。
3. strengths / weaknesses の本文には次の抽象語を使用禁止: 改善余地・訴求力・魅力・分かりやすさ・インパクト・工夫・仕掛け・チカラ・違和感
4. recommendations（改善提案）は必ず what / why / how の3点を書く。
   - what: 何を変えるか（対象と変更内容を具体的に。色・位置・文言・サイズ等、実際に手を動かせる粒度で）
   - why: なぜ変えるか（対応する weakness への言及を必ず含める。抽象論禁止）
   - how: どう検証するか（簡易な検証方法。ABテスト・比較指標など）
5. 各 recommendation は必ず target_weakness_ids で対応する weakness の id を最低1つ指定する。存在しない id を指定しない。
6. id は strengths は "s1","s2"...、weaknesses は "w1","w2"...、recommendations は "r1","r2"... のように短い連番文字列にする。
7. category は次の中から選ぶ: visual, message, cta, target, lp, brand
8. priority は weaknesses / recommendations ともに P0（致命的・即対応）/ P1（改善推奨）/ P2（伸び代）のいずれか。
9. 一般論・抽象論を避け、実際の制作・運用にそのまま渡せる粒度で書く（誰が読んでも次のアクションが分かること）。
10. strengths や weaknesses が本当に見当たらない場合は空配列 [] でよい。weaknesses が空なら recommendations も空配列でよい。
11. strengths / weaknesses には可能な限り evidence（分析データのどの部分からこの判断に至ったか、上記の評価観点のいずれかに触れる1文、40字程度まで）を付けること。分析データから読み取れる根拠が無い場合のみ省略してよい。
12. 各文は簡潔に（description/impact/evidence はいずれも1〜2文まで）。長文で説明するより、具体的な単語を選ぶことを優先する。

【JSON 出力フォーマット（必須・これ以外の説明文は一切含めない）】
{{
    "summary": {{
        "headline": "一言結論（例: LPとの連動は強いが、動画冒頭のフックが弱くCTRで機会損失）",
        "decision": "継続 または 改修推奨 または 停止検討",
        "rationale": "上記判断の理由（強み・弱みの要約）"
    }},
    "strengths": [
        {{
            "id": "s1",
            "category": "lp",
            "title": "LPとの完全一致",
            "description": "広告文とLPのファーストビューが『成約率2倍』で完全一致している",
            "keep_reason": "この整合性は信頼感とCVRに直結するため、今後の改修でも必ず維持すること",
            "evidence": "OCRテキストと構図から、広告とLPの数字訴求が一致していることを確認"
        }}
    ],
    "weaknesses": [
        {{
            "id": "w1",
            "priority": "P1",
            "category": "message",
            "title": "冒頭フックの抽象さ",
            "description": "動画冒頭3秒のテキストが抽象的で、視聴維持につながっていない",
            "impact": "スクロール離脱が増え、視聴完了率・CTRの両方を下げている",
            "evidence": "トーン情報の訴求軸が『イメージ訴求』のみでペインポイントへの言及が無い"
        }}
    ],
    "recommendations": [
        {{
            "id": "r1",
            "priority": "P1",
            "target_weakness_ids": ["w1"],
            "title": "冒頭ペインポイント訴求への変更",
            "what": "動画0〜3秒に『〜でお悩みですか？』というペインポイント訴求のテキストを大きく配置する",
            "why": "弱み『冒頭フックの抽象さ』を解消し、視聴維持率を上げるため",
            "how": "既存クリエイティブとABテストし、3秒視聴率とCTRを3日間比較する",
            "expected_effect": "3秒視聴率+10%、CTR改善を見込む"
        }}
    ]
}}

【出力注意】
- JSON 以外の説明文は一切含めない
- strengths / weaknesses / recommendations が 0 件の場合も配列構造は保持する（例: "strengths": []）
"""

    @staticmethod
    def generate_decision_support(
        creative_analysis: dict,
        model: str = "gpt"
    ) -> Union[DecisionSupport, LLMDecisionSupportValidationError]:
        """
        LLM で意思決定支援ブロック（強み・弱み・改善提案）を生成（再試行・バリデーション対応）

        既存の analyze_creative_improvements とは独立した呼び出しであり、
        本メソッドの失敗は diagnostics.improvements の生成には影響しない（fail-soft）。
        """
        from app.config import get_settings
        settings = get_settings()
        openai_api_key = settings.OPENAI_API_KEY
        if not openai_api_key and model == "gpt":
            return LLMDecisionSupportValidationError(
                success=False,
                error_code="API_KEY_MISSING",
                reason="OPENAI_API_KEY is not configured"
            )

        analysis_json = json.dumps(creative_analysis, ensure_ascii=False, indent=2)
        prompt = LLMService.DECISION_SUPPORT_PROMPT.format(analysis_data=analysis_json)

        for attempt in range(LLMService.MAX_RETRIES):
            try:
                if model == "gpt":
                    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
                    http_client = httpx.Client(proxy=proxy_url) if proxy_url else None
                    client = openai.OpenAI(api_key=openai_api_key, http_client=http_client)
                    response = client.chat.completions.create(
                        model=LLMService.GPT_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert ad creative decision-support analyst. Return only valid JSON."
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

                validator = LLMValidatorService()
                decision_support = validator.validate_decision_support(data)

                if isinstance(decision_support, DecisionSupport):
                    logger.info(f"Decision support generated successfully (attempt {attempt + 1})")
                    return decision_support
                else:
                    logger.warning(f"Decision support validation failed (attempt {attempt + 1}): {decision_support.reason}")
                    if attempt < LLMService.MAX_RETRIES - 1:
                        continue
                    else:
                        return decision_support

            except json.JSONDecodeError as e:
                logger.error(f"Decision support JSON parse error (attempt {attempt + 1}): {str(e)}")
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMDecisionSupportValidationError(
                        success=False,
                        error_code="JSON_PARSE_ERROR",
                        reason=f"Failed to parse LLM response as JSON: {str(e)}"
                    )

            except Exception as e:
                logger.error(f"Decision support LLM error (attempt {attempt + 1}): {str(e)}")
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMDecisionSupportValidationError(
                        success=False,
                        error_code="LLM_ERROR",
                        reason=f"LLM generation failed: {str(e)}"
                    )

        return LLMDecisionSupportValidationError(
            success=False,
            error_code="MAX_RETRIES_EXCEEDED",
            reason=f"Failed to generate valid decision support after {LLMService.MAX_RETRIES} attempts"
        )
