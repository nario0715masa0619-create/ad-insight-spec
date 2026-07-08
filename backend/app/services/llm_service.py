import os
import json
import re
import time
import base64
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
    EVALUATION_AXES,
    VideoCutAnalysis,
    LLMVideoCutAnalysisValidationError,
)
from app.services.llm_validator_service import LLMValidatorService
from app.services.text_mode_classifier import (
    TEXT_MODE_RICH,
    TEXT_MODE_ASR_ONLY,
)

logger = logging.getLogger(__name__)
# config.py から動的に読み込むため、トップレベルでの API キー初期化を削除
class LLMService:
    """GPT-4o（本命）と Gemini 2.0 Flash（比較対象）のデュアル実装"""
    
    GPT_MODEL = "gpt-4o"
    GEMINI_MODEL = "gemini-2.0-flash"
    MAX_RETRIES = 3
    # 特定の入力内容ではバリデーションに繰り返し失敗し、MAX_RETRIES 分の
    # リトライを毎回消費してしまうケースが実機で確認された（5軸診断1回あたり
    # 約20〜26秒 × 3回で70秒超）。累積リトライ時間がこの秒数を超えたら、
    # それ以上リトライせず fail-soft で打ち切る（本番のクライアント側
    # タイムアウトを引き起こさないための上限）。
    DECISION_SUPPORT_TIME_BUDGET_SECONDS = 50
    IMPROVEMENTS_TIME_BUDGET_SECONDS = 30
    VIDEO_CUTS_TIME_BUDGET_SECONDS = 50
    
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

        last_result: Union[ImprovementCommentsSchema, LLMImprovementValidationError, None] = None
        retry_start_time = time.time()

        # 再試行ループ（最大 3 回）
        for attempt in range(LLMService.MAX_RETRIES):
            # decision_support と同様、特定の入力内容でバリデーションに繰り返し
            # 失敗し続けるケースに備えて、累積時間が予算を超えたらリトライを打ち切る。
            elapsed = time.time() - retry_start_time
            if attempt > 0 and elapsed > LLMService.IMPROVEMENTS_TIME_BUDGET_SECONDS:
                logger.warning(
                    f"Improvements time budget exceeded after attempt {attempt} "
                    f"({elapsed:.1f}s > {LLMService.IMPROVEMENTS_TIME_BUDGET_SECONDS}s); stopping retries"
                )
                return last_result or LLMImprovementValidationError(
                    success=False,
                    error_code="TIME_BUDGET_EXCEEDED",
                    reason=f"Stopped retrying after {attempt} attempt(s) to stay within the time budget"
                )
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
                    last_result = improvements
                    if attempt < LLMService.MAX_RETRIES - 1:
                        continue
                    else:
                        return improvements  # 最後の試行で失敗 → エラー返却

            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error (attempt {attempt + 1}): {str(e)}")
                last_result = LLMImprovementValidationError(
                    success=False,
                    error_code="JSON_PARSE_ERROR",
                    reason=f"Failed to parse LLM response as JSON: {str(e)}"
                )
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return last_result
            
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

    # ===== 意思決定支援（decision_support: 5軸 × 強み・弱み・改善提案）生成 =====

    # 各軸の着眼点ガイド（旧来の6観点を5軸に再配分）。プロンプト内の軸列挙に使う。
    _AXIS_VIEWPOINT_GUIDE = {
        "appeal": "メッセージの核は何か。誰の何の悩み/欲求に刺さる設計か（訴求軸）",
        "creative": "視線が集まりやすい要素（色・サイズ・配置）から情報がどの順で伝わるか。"
                    "テキスト量・コントラスト・フォントサイズ感が情報を読み取れる設計か（視線誘導・可読性）",
        "cta": "強さ・視認性・行動喚起の具体性（次に何をすればいいか一目で分かるか）",
        "trust": "具体的な数字・社会的証明・権威性等、信じるに足る根拠が示されているか。"
                 "競合の一般的な訴求と比べて何が独自か、埋もれていないか（信頼性・差別化）",
        "target": "想定される視聴者/読者のペルソナに対して、訴求内容・トーン・フォーマットが噛み合っているか",
    }

    DECISION_SUPPORT_PROMPT = """
あなたは広告クリエイティブの意思決定支援を行う専門家です。
以下のクリエイティブ分析結果をもとに、広告運用の専門家とは限らない担当者が
「配信を続けるか改修するか」「次に何から着手するか」を5秒で判断できるよう、
固定の5軸（訴求軸・クリエイティブ・CTA・信頼・ターゲット）それぞれについて、
強み・弱み・改善提案を JSON 形式で構造化してください。
{previous_feedback}
{text_mode_guidance}
【分析対象情報（CreativeCore）】
{analysis_data}

【評価する5軸（必ずこの5つ全てを axis id のまま出力すること。過不足・重複は禁止）】
{axis_guide}

【必須ルール】
1. axes 配列には必ず上記5軸をちょうど1件ずつ、この順で出力する。
2. 各軸の strength（強み）は「今後も維持・再利用すべき勝ち要素」として書く。単なる褒め言葉（「良い」「魅力的」等）は禁止。
3. 各軸の weakness（弱み）は成果の足を引っ張っているボトルネックとして書く。
4. strength / weakness の description・reason・impact には次の抽象語を使用禁止: 改善余地・訴求力・魅力・分かりやすさ・インパクト・工夫・仕掛け・チカラ・違和感
5. strength / weakness には必ず target_element（対象要素の特定。例: 「ファーストビューのテキスト」「動画5〜8秒目」「CTAボタン文言」等）を書く。
6. strength / weakness には必ず reason（そう判断した理由。ユーザー心理や一般的なベストプラクティスの観点で書く。抽象論禁止）を書く。
7. strength / weakness の evidence は必ず4点セットで書く: location（対象箇所。テキスト抜粋や動画タイムスタンプ等、後から見返しても位置が分かる形式）/ viewpoint（評価観点）/ evaluation（その観点からの評価）/ rationale（根拠）。
8. recommendation は必ず what / why / how / expected_effect の4点を書く。
   - what: 何を変えるか（対象と変更内容を具体的に。色・位置・文言・サイズ等、実際に手を動かせる粒度で）
   - why: なぜ変えるか（同じ軸の weakness への言及を必ず含める。抽象論禁止）
   - how: どう検証するか（簡易な検証方法。ABテスト・比較指標など）
   - expected_effect: 期待される効果を具体的な指標で書く（例: 理解速度向上、CVR改善、CTR向上、視聴維持率向上等。数値目安があれば含める）
9. score は 1〜5 の整数（この軸の現状評価。5が最良）。
10. 一般論・抽象論を避け、実際の制作・運用にそのまま渡せる粒度で書く（誰が読んでも次のアクションが分かること）。
11. 各文は簡潔に（description/impact/reason/evidence の各項目はいずれも1〜2文まで）。長文で説明するより、具体的な単語を選ぶことを優先する。
12. summary.headline は「判定：一番の問題点」の定型形式で15〜20字程度の短い見出しにする（例: 「改善優先：信頼訴求が弱い」「要改善：CTAの具体性不足」「良好：訴求と信頼のバランスが良い」）。詳しい説明文は headline ではなく rationale に書く。headline を長文の説明文にしない。
13. strength / weakness には必ず aspect（評価観点の短いラベル、2〜15字程度。例: 「トーンの印象」「証拠・差別化」「ペルソナ具体性」等）を書く。同一軸内で strength.aspect と weakness.aspect は必ず異なる観点にすること（同じ観点を強み・弱み双方に置いてはいけない。例: 信頼軸で strength.aspect が「信頼性」、weakness.aspect も「信頼性」は禁止）。
14. strength は「今後も維持すべき良さ」だけを書き、weakness は strength とは別の観点で「改善すべき点」だけを書く。同じ観点について「良い面もあるが悪い面もある」という両論併記はしない。
15. score とのバランス: score が4以上の軸は、weakness があっても軽微な注意点に留め、致命的な弱点は書かない。score が2以下の軸は、strength を「現状維持すべき最低限の良さ」1点に絞る（過度に持ち上げない）。score が3の軸は strength / weakness とも意味のある内容でよいが、13のとおり aspect は必ず別にする。
16. summary.rationale は、axes のうち最もスコアが低い軸（同点の場合は appeal→creative→cta→trust→target の順で先の軸）の weakness.aspect を主題にして書く。他の軸の strength の内容を rationale に持ち込まない。

【JSON 出力フォーマット（必須・これ以外の説明文は一切含めない。1軸分の例）】
{{
    "summary": {{
        "headline": "短い見出し（例: 「改善優先：信頼訴求が弱い」「要改善：CTAの具体性不足」のような判定＋一番の問題点の定型形式、15〜20字程度）",
        "decision": "継続 または 改修推奨 または 停止検討",
        "rationale": "headline の判定に至った理由を1〜2文で（例: LPとの連動は強いが、動画冒頭のフックが弱くCTRで機会損失している）"
    }},
    "axes": [
        {{
            "axis": "appeal",
            "axis_label": "訴求軸",
            "score": 4,
            "strength": {{
                "target_element": "ファーストビューのキャッチコピー",
                "aspect": "数字訴求の具体性",
                "description": "『成約率2倍』という具体的な数字でペインポイントに直接応えている",
                "reason": "具体的な数字は抽象的な訴求より信頼されやすく、意思決定を後押しするため",
                "keep_reason": "この数字訴求は信頼感とCVRに直結するため、今後の改修でも必ず維持すること",
                "evidence": {{
                    "location": "ファーストビューのテキスト『成約率2倍』",
                    "viewpoint": "訴求軸",
                    "evaluation": "具体的な数字による訴求で説得力が高い",
                    "rationale": "OCRテキストからこの数字訴求が最初に視認される位置にあることを確認"
                }}
            }},
            "weakness": {{
                "target_element": "動画冒頭0〜3秒のテキスト",
                "aspect": "冒頭フックの具体性",
                "description": "抽象的な言い回しで、視聴維持につながっていない",
                "reason": "冒頭3秒で具体的なペインポイントを提示しないと離脱が増えるのが一般的なベストプラクティスのため",
                "impact": "スクロール離脱が増え、視聴完了率・CTRの両方を下げている",
                "evidence": {{
                    "location": "動画0〜3秒目",
                    "viewpoint": "訴求軸",
                    "evaluation": "ペインポイントへの言及が無く抽象的",
                    "rationale": "トーン情報の訴求軸が『イメージ訴求』のみで具体的な悩みへの言及が無いことを確認"
                }}
            }},
            "recommendation": {{
                "what": "動画0〜3秒に『〜でお悩みですか？』というペインポイント訴求のテキストを大きく配置する",
                "why": "同軸の弱み『冒頭フックの抽象さ』を解消し、視聴維持率を上げるため",
                "how": "既存クリエイティブとABテストし、3秒視聴率とCTRを3日間比較する",
                "expected_effect": "3秒視聴率+10%、CTR改善を見込む"
            }}
        }}
    ]
}}

【出力注意】
- JSON 以外の説明文は一切含めない
- axes は必ず5件（appeal, creative, cta, trust, target を過不足なく1件ずつ）
"""

    @staticmethod
    def _apply_overall_score(decision_support: DecisionSupport) -> None:
        """
        axes のスコア平均から overall_score / overall_rank を算出してセットする。
        LLM 出力を信頼せず、必ず Python 側の計算値で上書きする。
        """
        scores = [axis.score for axis in decision_support.axes]
        overall_score = sum(scores) / len(scores) if scores else 0.0
        if overall_score >= 4.5:
            overall_rank = "A"
        elif overall_score >= 3.5:
            overall_rank = "B"
        elif overall_score >= 2.5:
            overall_rank = "C"
        else:
            overall_rank = "D"
        decision_support.overall_score = round(overall_score, 2)
        decision_support.overall_rank = overall_rank

    # ===== 5軸診断のテキスト入力モード別ガイダンス =====
    # 「テロップ無し・音声ナレーションあり」動画でもASRを主情報源として
    # 5軸診断を有効化するための、モード別プロンプト差し込み文。
    _TEXT_MODE_ASR_ONLY_GUIDANCE = """
【重要: この動画は明示的なテロップ（画面上テキスト）がほとんどありません】
以下の「音声の文字起こし（ASR）」を、この5軸診断の主な情報源として扱ってください。
- この動画は意図的にテロップを使わない構成である可能性があります。
- 改善提案では、テロップの追加を安易に推奨しないでください。
- 映像の構成・ストーリーテリング・テンポ・音声の伝え方など、テキスト以外の
  要素についても積極的に改善提案を行ってください。
- 上記ルールや出力フォーマット中の「テロップ」「画面上のテキスト」という
  表現は、この動画では「ナレーション」「音声で伝えられているメッセージ」と
  読み替えて評価してください。

【音声の文字起こし（ASR）】
{asr_text}
"""

    _TEXT_MODE_RICH_WITH_ASR_GUIDANCE = """
【参考情報】
以下は音声の文字起こし（ASR）です。画面上テキストを主な情報源とし、
これはあくまで補助的な参考情報として扱ってください。

{asr_text}
"""

    @staticmethod
    def _build_text_mode_guidance(text_mode: str, asr_text: Optional[str]) -> str:
        """text_mode/asr_textから、DECISION_SUPPORT_PROMPTに差し込むガイダンス文を組み立てる。"""
        if text_mode == TEXT_MODE_ASR_ONLY and asr_text:
            return LLMService._TEXT_MODE_ASR_ONLY_GUIDANCE.format(asr_text=asr_text)
        if asr_text:
            # RICHだがasr_textが渡された場合（保険的なケース）: 補助情報として添付するのみ
            return LLMService._TEXT_MODE_RICH_WITH_ASR_GUIDANCE.format(asr_text=asr_text)
        return ""

    @staticmethod
    def generate_decision_support(
        creative_analysis: dict,
        text_mode: str = TEXT_MODE_RICH,
        asr_text: Optional[str] = None,
        model: str = "gpt"
    ) -> Union[DecisionSupport, LLMDecisionSupportValidationError]:
        """
        LLM で意思決定支援ブロック（5軸 × 強み・弱み・改善提案）を生成（再試行・バリデーション対応）

        既存の analyze_creative_improvements とは独立した呼び出しであり、
        本メソッドの失敗は diagnostics.improvements の生成には影響しない（fail-soft）。

        text_mode: TEXT_MODE_RICH（既定・画像や旧来動作）/ TEXT_MODE_ASR_ONLY
                   （テロップ無し・ASR主体）。呼び出し側（analysis_orchestrator）が
                   text_mode_classifier.classify_text_mode で判定して渡す。
        asr_text: text_mode=TEXT_MODE_ASR_ONLY の場合の音声文字起こし本文。
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
        axis_guide = "\n".join(
            f"- {axis_label}（{axis_id}）: {LLMService._AXIS_VIEWPOINT_GUIDE[axis_id]}"
            for axis_id, axis_label in EVALUATION_AXES
        )
        text_mode_guidance = LLMService._build_text_mode_guidance(text_mode, asr_text)

        # 前回リトライで失敗した理由をプロンプトに差し込むことで、同じ間違いを
        # 繰り返さず1〜2回目で通る確率を上げる（リトライ回数そのものを減らす）。
        # 初回は空文字列。
        previous_feedback = ""
        last_result: Union[DecisionSupport, LLMDecisionSupportValidationError, None] = None
        retry_start_time = time.time()

        for attempt in range(LLMService.MAX_RETRIES):
            # 特定の入力内容ではバリデーションに繰り返し失敗し、MAX_RETRIES 分を
            # 毎回消費してしまうケースを実機で確認した（1回あたり約20〜26秒 ×
            # 3回で70秒超）。累積時間が予算を超えたら、それ以上リトライせず
            # 直近の結果を fail-soft で返す。
            elapsed = time.time() - retry_start_time
            if attempt > 0 and elapsed > LLMService.DECISION_SUPPORT_TIME_BUDGET_SECONDS:
                logger.warning(
                    f"Decision support time budget exceeded after attempt {attempt} "
                    f"({elapsed:.1f}s > {LLMService.DECISION_SUPPORT_TIME_BUDGET_SECONDS}s); stopping retries"
                )
                return last_result or LLMDecisionSupportValidationError(
                    success=False,
                    error_code="TIME_BUDGET_EXCEEDED",
                    reason=f"Stopped retrying after {attempt} attempt(s) to stay within the time budget"
                )

            prompt = LLMService.DECISION_SUPPORT_PROMPT.format(
                analysis_data=analysis_json,
                axis_guide=axis_guide,
                previous_feedback=previous_feedback,
                text_mode_guidance=text_mode_guidance,
            )
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
                        # 5軸 × (strength/weakness/recommendation + evidence 4点セット) は
                        # 旧来のフラット形式より出力量が大幅に増えるため、2000だと打ち切られてJSON
                        # パースエラーになることを実機確認済み。4000へ引き上げる。
                        max_tokens=4000
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
                    LLMService._apply_overall_score(decision_support)
                    logger.info(f"Decision support generated successfully (attempt {attempt + 1})")
                    return decision_support
                else:
                    logger.warning(f"Decision support validation failed (attempt {attempt + 1}): {decision_support.reason}")
                    last_result = decision_support
                    previous_feedback = (
                        "\n【前回の出力が却下された理由（同じ間違いを繰り返さないこと）】\n"
                        f"{decision_support.reason}\n"
                    )
                    if attempt < LLMService.MAX_RETRIES - 1:
                        continue
                    else:
                        return decision_support

            except json.JSONDecodeError as e:
                logger.error(f"Decision support JSON parse error (attempt {attempt + 1}): {str(e)}")
                last_result = LLMDecisionSupportValidationError(
                    success=False,
                    error_code="JSON_PARSE_ERROR",
                    reason=f"Failed to parse LLM response as JSON: {str(e)}"
                )
                previous_feedback = (
                    "\n【前回の出力が却下された理由（同じ間違いを繰り返さないこと）】\n"
                    "有効なJSONとしてパースできませんでした。JSON以外の説明文を含めず、"
                    "指定されたフォーマットのJSONのみを出力してください。\n"
                )
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return last_result

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

    # ===== カット別分析（video_cuts）生成 =====
    # decision_support/improvements と異なり、この呼び出しだけは実際の代表
    # フレーム画像をVision APIに添付する（他の分析はテキストのみで、
    # 「画面内容」の記述は実質推測になっているため、カット別分析では
    # 実際の画面を根拠にした具体性を優先する）。

    VIDEO_CUT_ANALYSIS_PROMPT = """
あなたは広告クリエイティブの動画カット分析を行う専門家です。
添付された画像は、この動画を複数のカット（ショット）に分割した際の、
各カットの代表フレームです（画像は下記リストの順序で対応しています）。

【各カットの情報】
{cut_info}

【必須ルール】
1. 添付された実際の画像を見て判断すること。画像から読み取れない内容を想像や一般論で埋めない。
2. role_tag は、次の6つの内部語彙のうち最も当てはまるものを1つだけ選ぶ（この単語をそのまま出力する。他の表現に言い換えない）:
   - hook: 冒頭で視線を引きつけるカット
   - benefit: 商品・サービスのベネフィットを提示するカット
   - proof: 実績・データ・使用例など証拠を提示するカット
   - trust: 権威性・保証・レビュー等で信頼を形成するカット
   - cta: 行動喚起（購入・登録・タップ等）を促すカット
   - other: 上記のいずれにも当てはまらないカット
3. summary は画面に実際に映っている内容を具体的に書く（人物・商品・テキスト・構図など、1〜2文）。
4. improvement_suggestion は、そのカットに対する具体的な改善提案を1〜2行で書く（そのまま制作指示に使える粒度で）。
5. strength_or_issue は、そのカットの強み、または問題点のどちらかを1〜2行で具体的に書く（可能な範囲で。省略可）。
6. evidence は、判断の簡単な根拠を1文で書く（画面のどの部分から読み取ったか。省略可）。
7. 次の抽象語を使用禁止: 改善余地・訴求力・魅力・分かりやすさ・インパクト・工夫・仕掛け・チカラ・違和感
8. cut_id は与えられたIDをそのまま使う（新しいIDを作らない。全カット分を過不足なく出力する）。

【JSON出力フォーマット（必須・これ以外の説明文は一切含めない）】
{{
    "cuts": [
        {{
            "cut_id": "cut_1",
            "role_tag": "hook",
            "summary": "画面に映っている具体的な内容",
            "improvement_suggestion": "具体的な改善提案",
            "strength_or_issue": "強みまたは問題点",
            "evidence": "判断の根拠"
        }}
    ]
}}
"""

    @staticmethod
    def analyze_video_cuts(
        video_cuts: list,
        model: str = "gpt"
    ) -> Union[VideoCutAnalysis, LLMVideoCutAnalysisValidationError]:
        """
        動画のカットごとに、代表フレーム画像を実際にVision APIへ送って
        役割・要約・強み/問題点・改善提案を生成する（再試行・バリデーション対応）。

        Args:
            video_cuts: [{"cut_id": str, "start_seconds": float, "end_seconds": float,
                          "frame_path": str, "ocr_text": str}, ...]
                        （時間範囲・代表フレームはバックエンド側で確定済み。
                        LLMには時間範囲を再生成させない）
            model: "gpt"（Vision対応） または "gemini"

        既存の improvements/decision_support とは独立した呼び出しであり、
        本メソッドの失敗は他の診断結果には影響しない（fail-soft）。
        """
        if not video_cuts:
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="NO_CUTS",
                reason="No video cuts to analyze"
            )

        from app.config import get_settings
        settings = get_settings()
        openai_api_key = settings.OPENAI_API_KEY
        if not openai_api_key and model == "gpt":
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="API_KEY_MISSING",
                reason="OPENAI_API_KEY is not configured"
            )

        known_cut_ids = [c["cut_id"] for c in video_cuts]

        # フレーム画像を base64 エンコード（読み込めないフレームはスキップし、
        # 該当カットはLLMに送らない＝バリデーションの known_cut_ids からも除外）
        encoded_frames = []
        for cut in video_cuts:
            frame_path = cut.get("frame_path")
            if not frame_path:
                continue
            try:
                with open(frame_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                encoded_frames.append((cut, b64))
            except Exception as e:
                logger.warning(f"Failed to read cut frame {frame_path}: {str(e)}")

        if not encoded_frames:
            return LLMVideoCutAnalysisValidationError(
                success=False,
                error_code="NO_FRAMES",
                reason="No cut frames could be read for analysis"
            )
        known_cut_ids = [cut["cut_id"] for cut, _ in encoded_frames]

        cut_info_lines = []
        for cut, _ in encoded_frames:
            ocr_text = cut.get("ocr_text") or "（テキストなし）"
            cut_info_lines.append(
                f"- {cut['cut_id']}（{cut['start_seconds']:.1f}〜{cut['end_seconds']:.1f}秒）"
                f" 画面内OCRテキスト: {ocr_text}"
            )
        cut_info = "\n".join(cut_info_lines)

        previous_feedback = ""
        last_result: Union[VideoCutAnalysis, LLMVideoCutAnalysisValidationError, None] = None
        retry_start_time = time.time()

        for attempt in range(LLMService.MAX_RETRIES):
            elapsed = time.time() - retry_start_time
            if attempt > 0 and elapsed > LLMService.VIDEO_CUTS_TIME_BUDGET_SECONDS:
                logger.warning(
                    f"Video cuts time budget exceeded after attempt {attempt} "
                    f"({elapsed:.1f}s > {LLMService.VIDEO_CUTS_TIME_BUDGET_SECONDS}s); stopping retries"
                )
                return last_result or LLMVideoCutAnalysisValidationError(
                    success=False,
                    error_code="TIME_BUDGET_EXCEEDED",
                    reason=f"Stopped retrying after {attempt} attempt(s) to stay within the time budget"
                )

            prompt_text = LLMService.VIDEO_CUT_ANALYSIS_PROMPT.format(cut_info=cut_info) + previous_feedback

            try:
                if model == "gpt":
                    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
                    http_client = httpx.Client(proxy=proxy_url) if proxy_url else None
                    client = openai.OpenAI(api_key=openai_api_key, http_client=http_client)

                    content = [{"type": "text", "text": prompt_text}]
                    for cut, b64 in encoded_frames:
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"},
                        })

                    response = client.chat.completions.create(
                        model=LLMService.GPT_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert ad creative video analyst. Return only valid JSON."
                            },
                            {"role": "user", "content": content}
                        ],
                        temperature=0.7,
                        max_tokens=3000
                    )
                    response_text = response.choices[0].message.content
                else:  # gemini
                    import PIL.Image
                    model_obj = genai.GenerativeModel(LLMService.GEMINI_MODEL)
                    parts = [prompt_text]
                    for cut, _ in encoded_frames:
                        parts.append(PIL.Image.open(cut["frame_path"]))
                    response = model_obj.generate_content(parts)
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
                video_cut_analysis = validator.validate_video_cuts(data, known_cut_ids)

                if isinstance(video_cut_analysis, VideoCutAnalysis):
                    logger.info(f"Video cut analysis generated successfully (attempt {attempt + 1})")
                    return video_cut_analysis
                else:
                    logger.warning(
                        f"Video cut analysis validation failed (attempt {attempt + 1}): {video_cut_analysis.reason}"
                    )
                    last_result = video_cut_analysis
                    previous_feedback = (
                        "\n【前回の出力が却下された理由（同じ間違いを繰り返さないこと）】\n"
                        f"{video_cut_analysis.reason}\n"
                    )
                    if attempt < LLMService.MAX_RETRIES - 1:
                        continue
                    else:
                        return video_cut_analysis

            except json.JSONDecodeError as e:
                logger.error(f"Video cut analysis JSON parse error (attempt {attempt + 1}): {str(e)}")
                last_result = LLMVideoCutAnalysisValidationError(
                    success=False,
                    error_code="JSON_PARSE_ERROR",
                    reason=f"Failed to parse LLM response as JSON: {str(e)}"
                )
                previous_feedback = (
                    "\n【前回の出力が却下された理由（同じ間違いを繰り返さないこと）】\n"
                    "有効なJSONとしてパースできませんでした。JSON以外の説明文を含めず、"
                    "指定されたフォーマットのJSONのみを出力してください。\n"
                )
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return last_result

            except Exception as e:
                logger.error(f"Video cut analysis LLM error (attempt {attempt + 1}): {str(e)}")
                if attempt < LLMService.MAX_RETRIES - 1:
                    continue
                else:
                    return LLMVideoCutAnalysisValidationError(
                        success=False,
                        error_code="LLM_ERROR",
                        reason=f"LLM generation failed: {str(e)}"
                    )

        return LLMVideoCutAnalysisValidationError(
            success=False,
            error_code="MAX_RETRIES_EXCEEDED",
            reason=f"Failed to generate valid video cut analysis after {LLMService.MAX_RETRIES} attempts"
        )
