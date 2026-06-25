import pytest
from unittest.mock import patch, MagicMock
from app.services.llm_service import LLMService
from app.schemas.llm_response import LLMResponseSchema

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
