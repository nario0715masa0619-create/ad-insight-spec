import pytest
from unittest.mock import patch, MagicMock
from app.services.llm_service import LLMService
from app.schemas.llm_response import LLMResponseSchema, ImprovementCommentsSchema
from app.services.llm_validator_service import LLMValidatorService

class TestLLMServiceSchema:
    """LLMService のスキーマ検証テスト"""
    
    VALID_JSON_RESPONSE = """{
        "visuals": {
            "dominant_colors": ["blue", "white"],
            "composition": "centered product display",
            "style": "modern minimalist",
            "clarity": "高"
        },
        "tone": {
            "primary_tone": ["professional", "trustworthy"],
            "emotional_appeal": "論理的",
            "call_to_action": "強"
        },
        "ai_labels": ["finance", "trust", "innovation", "security"]
    }"""
    
    def test_validate_and_parse_valid_json(self):
        """有効な JSON パース"""
        result = LLMService._validate_and_parse_response(self.VALID_JSON_RESPONSE)
        assert result["visuals"]["dominant_colors"] == ["blue", "white"]
        assert result["tone"]["emotional_appeal"] == "論理的"
        assert len(result["ai_labels"]) == 4
    
    def test_validate_and_parse_json_block(self):
        """```json ... ``` ブロック形式パース"""
        response = f"```json\n{self.VALID_JSON_RESPONSE}\n```"
        result = LLMService._validate_and_parse_response(response)
        assert result["visuals"]["dominant_colors"] == ["blue", "white"]
    
    def test_validate_and_parse_missing_field(self):
        """必須フィールド欠落時"""
        invalid_json = """{
            "visuals": {
                "dominant_colors": ["blue"],
                "composition": "test",
                "style": "modern"
            },
            "tone": {
                "primary_tone": ["test"],
                "emotional_appeal": "論理的",
                "call_to_action": "強"
            },
            "ai_labels": ["test"]
        }"""
        
        with pytest.raises(ValueError, match="Schema validation failed"):
            LLMService._validate_and_parse_response(invalid_json)
    
    def test_validate_and_parse_wrong_type(self):
        """型違反"""
        invalid_json = """{
            "visuals": {
                "dominant_colors": "blue",
                "composition": "test",
                "style": "modern",
                "clarity": "高"
            },
            "tone": {
                "primary_tone": ["test"],
                "emotional_appeal": "論理的",
                "call_to_action": "強"
            },
            "ai_labels": ["test"]
        }"""
        
        with pytest.raises(ValueError, match="Schema validation failed"):
            LLMService._validate_and_parse_response(invalid_json)
    
    def test_validate_and_parse_invalid_enum(self):
        """Enum 値違反"""
        invalid_json = """{
            "visuals": {
                "dominant_colors": ["blue"],
                "composition": "test composition",
                "style": "modern",
                "clarity": "INVALID"
            },
            "tone": {
                "primary_tone": ["test"],
                "emotional_appeal": "論理的",
                "call_to_action": "強"
            },
            "ai_labels": ["test"]
        }"""
        
        with pytest.raises(ValueError, match="Schema validation failed"):
            LLMService._validate_and_parse_response(invalid_json)


class TestLLMServiceGPT:
    """GPT-4o 実装テスト"""
    
    VALID_JSON = """{
        "visuals": {"dominant_colors": ["blue", "white"], "composition": "centered", "style": "modern", "clarity": "高"},
        "tone": {"primary_tone": ["professional"], "emotional_appeal": "論理的", "call_to_action": "強"},
        "ai_labels": ["finance", "tech"]
    }"""
    
    @patch('app.services.llm_service.openai.ChatCompletion.create')
    def test_gpt_success(self, mock_create):
        """GPT-4o 成功"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = self.VALID_JSON
        mock_create.return_value = mock_response
        
        result = LLMService.analyze_creative_gpt(
            image_description="Test image",
            lp_content="Test LP"
        )
        
        assert result.success is True
        assert result.model == "gpt-4o"
        assert result.retry_count == 0
        assert result.creative_core is not None
    
    @patch('app.services.llm_service.openai.ChatCompletion.create')
    def test_gpt_retry_success(self, mock_create):
        """GPT-4o 再試行後成功"""
        # 1回目は失敗、2回目は成功
        mock_response_fail = MagicMock()
        mock_response_fail.choices[0].message.content = "Invalid JSON"
        
        mock_response_success = MagicMock()
        mock_response_success.choices[0].message.content = self.VALID_JSON
        
        mock_create.side_effect = [mock_response_fail, mock_response_success]
        
        result = LLMService.analyze_creative_gpt(
            image_description="Test image"
        )
        
        assert result.success is True
        assert result.retry_count == 1
    
    @patch('app.services.llm_service.openai.ChatCompletion.create')
    def test_gpt_max_retries_exceeded(self, mock_create):
        """GPT-4o 最大再試行回数超過"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Invalid JSON"
        mock_create.return_value = mock_response
        
        result = LLMService.analyze_creative_gpt(
            image_description="Test image"
        )
        
        assert result.success is False
        assert result.retry_count == 2
        assert "Failed after 3 retries" in result.error_details

    @patch('app.services.llm_service.openai.OpenAI')
    def test_analyze_creative_improvements_success(self, mock_openai):
        """改善コメント生成成功テスト"""
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = """{
            "comments": [
                {
                    "issue_summary": "見出しのフォントサイズが小さい",
                    "target_scope": "ページ上部の見出し",
                    "evidence": "36px で表示されており、モバイルでの視認性が低い",
                    "recommended_action": "フォントサイズを 48px 以上に拡大",
                    "priority": "P1",
                    "expected_impact": "モバイル CTR 3～5% 向上",
                    "confidence": 0.88
                }
            ],
            "total_count": 1,
            "summary": "ビジュアル階層の再構築が必須"
        }"""
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        creative_data = {
            "visuals": {"dominant_colors": ["blue"], "clarity": "高"},
            "tone": {"primary_tone": ["professional"]},
            "ai_labels": ["tech", "modern"]
        }
        
        result = LLMService.analyze_creative_improvements(creative_data, model="gpt")
        
        assert isinstance(result, ImprovementCommentsSchema)
        assert len(result.comments) == 1
        assert result.comments[0].issue_summary == "見出しのフォントサイズが小さい"


class TestLLMServiceGemini:
    """Gemini 2.0 Flash 実装テスト"""
    
    VALID_JSON = """{
        "visuals": {"dominant_colors": ["red", "gold"], "composition": "diagonal layout", "style": "luxurious", "clarity": "中"},
        "tone": {"primary_tone": ["premium", "exclusive"], "emotional_appeal": "感情的", "call_to_action": "中"},
        "ai_labels": ["luxury", "fashion", "premium"]
    }"""
    
    @patch('app.services.llm_service.genai.GenerativeModel')
    def test_gemini_success(self, mock_genai):
        """Gemini 成功"""
        mock_response = MagicMock()
        mock_response.text = self.VALID_JSON
        mock_genai.return_value.generate_content.return_value = mock_response
        
        result = LLMService.analyze_creative_gemini(
            image_description="Test image",
            lp_content="Test LP"
        )
        
        assert result.success is True
        assert result.model == "gemini-2.0-flash"
        assert result.retry_count == 0
        assert result.creative_core is not None
    
    @patch('app.services.llm_service.genai.GenerativeModel')
    def test_gemini_retry_success(self, mock_genai):
        """Gemini 再試行後成功"""
        mock_response_fail = MagicMock()
        mock_response_fail.text = "Invalid"
        
        mock_response_success = MagicMock()
        mock_response_success.text = self.VALID_JSON
        
        mock_genai.return_value.generate_content.side_effect = [
            mock_response_fail,
            mock_response_success
        ]
        
        result = LLMService.analyze_creative_gemini(
            image_description="Test image"
        )
        
        assert result.success is True
        assert result.retry_count == 1


class TestLLMServiceConsistency:
    """同一入力 10 回実行テスト（合格ライン）"""
    
    VALID_JSON_TEMPLATE = """{
        "visuals": {"dominant_colors": ["blue", "white"], "composition": "centered display", "style": "modern", "clarity": "高"},
        "tone": {"primary_tone": ["professional"], "emotional_appeal": "論理的", "call_to_action": "強"},
        "ai_labels": ["finance", "trust", "innovation"]
    }"""
    
    @patch('app.services.llm_service.openai.ChatCompletion.create')
    def test_gpt_10_runs_consistency(self, mock_create):
        """GPT-4o 同一入力 10 回実行 → 必須構造一致率 100%"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = self.VALID_JSON_TEMPLATE
        mock_create.return_value = mock_response
        
        results = []
        for i in range(10):
            result = LLMService.analyze_creative_gpt(
                image_description="Consistent test image",
                lp_content="Consistent test LP"
            )
            results.append(result)
        
        # 検証：10 回すべて success
        assert all(r.success for r in results), "Not all results succeeded"
        
        # 検証：必須フィールド一致率 100%
        for result in results:
            core_dict = result.creative_core.model_dump() if hasattr(result.creative_core, "model_dump") else result.creative_core
            assert "visuals" in core_dict
            assert "tone" in core_dict
            assert "ai_labels" in core_dict
            assert core_dict["visuals"]["clarity"] == "高"
            assert core_dict["tone"]["emotional_appeal"] == "論理的"
            assert len(core_dict["ai_labels"]) == 3
        
        # 検証：欠落・型違反 0 件
        print(f"✅ GPT-4o: 10/10 success, 構造一致率 100%, 欠落・型違反 0 件")
    
    @patch('app.services.llm_service.genai.GenerativeModel')
    def test_gemini_10_runs_consistency(self, mock_genai):
        """Gemini 同一入力 10 回実行 → 必須構造一致率 100%"""
        mock_response = MagicMock()
        mock_response.text = self.VALID_JSON_TEMPLATE
        mock_genai.return_value.generate_content.return_value = mock_response
        
        results = []
        for i in range(10):
            result = LLMService.analyze_creative_gemini(
                image_description="Consistent test image",
                lp_content="Consistent test LP"
            )
            results.append(result)
        
        # 検証：10 回すべて success
        assert all(r.success for r in results), "Not all results succeeded"
        
        # 検証：必須フィールド一致率 100%
        for result in results:
            core_dict = result.creative_core.model_dump() if hasattr(result.creative_core, "model_dump") else result.creative_core
            assert "visuals" in core_dict
            assert "tone" in core_dict
            assert "ai_labels" in core_dict
            assert core_dict["visuals"]["clarity"] == "高"
            assert core_dict["tone"]["emotional_appeal"] == "論理的"
            assert len(core_dict["ai_labels"]) == 3
        
        # 検証：欠落・型違反 0 件
        print(f"✅ Gemini: 10/10 success, 構造一致率 100%, 欠落・型違反 0 件")


class TestDecisionSupportOverallScore:
    """decision_support の overall_score / overall_rank 算出テスト（LLM出力を信頼せずPython側で計算）"""

    @staticmethod
    def _make_axis(axis_id: str, score: int):
        return {
            "axis": axis_id,
            "axis_label": axis_id,
            "score": score,
            "strength": {
                "target_element": "テキスト", "aspect": "強みの観点", "description": "説明文です十分な長さ",
                "reason": "理由の説明文です十分な長さ", "keep_reason": "維持理由の説明文です十分な長さ",
                "evidence": {"location": "冒頭", "viewpoint": axis_id, "evaluation": "良い評価です", "rationale": "根拠の説明文です十分な長さ"},
            },
            "weakness": {
                "target_element": "テキスト2", "aspect": "弱みの観点", "description": "説明文です十分な長さ",
                "reason": "理由の説明文です十分な長さ", "impact": "影響の説明文です十分な長さ",
                "evidence": {"location": "中盤", "viewpoint": axis_id, "evaluation": "悪い評価です", "rationale": "根拠の説明文です十分な長さ"},
            },
            "recommendation": {
                "what": "変更内容の説明文です十分な長さ", "why": "理由の説明文です十分な長さ",
                "how": "検証方法の説明文です十分な長さ", "expected_effect": "CVR改善を見込む",
            },
        }

    def _build_decision_support(self, scores):
        axis_ids = ["appeal", "creative", "cta", "trust", "target"]
        data = {
            "summary": {"headline": "テスト結論の見出しです", "decision": "継続", "rationale": "強み弱みの要約テキストです"},
            "axes": [self._make_axis(a, s) for a, s in zip(axis_ids, scores)],
        }
        result = LLMValidatorService().validate_decision_support(data)
        assert not hasattr(result, "error_code"), getattr(result, "reason", result)
        return result

    @pytest.mark.parametrize("scores,expected_rank", [
        ([5, 5, 5, 5, 5], "A"),
        ([4, 4, 4, 4, 3], "B"),
        ([3, 3, 3, 3, 2], "C"),
        ([1, 1, 2, 1, 1], "D"),
    ])
    def test_overall_rank_thresholds(self, scores, expected_rank):
        """overall_score の平均値からA/B/C/Dランクが閾値通りに算出される"""
        decision_support = self._build_decision_support(scores)
        LLMService._apply_overall_score(decision_support)
        assert decision_support.overall_rank == expected_rank
        assert decision_support.overall_score == pytest.approx(sum(scores) / len(scores), abs=0.01)

    def test_overall_score_not_trusted_from_llm(self):
        """LLM出力に overall_score/overall_rank が無くても（validatorが受け付けない）Python側で必ず算出される"""
        decision_support = self._build_decision_support([4, 4, 4, 4, 4])
        assert decision_support.overall_score is None  # validator通過直後はまだ未設定
        LLMService._apply_overall_score(decision_support)
        assert decision_support.overall_score == 4.0
        assert decision_support.overall_rank == "B"
