import pytest
from unittest.mock import patch, MagicMock
from app.services.llm_service import LLMService

class TestLLMService:
    """LLMService の単体テスト"""
    
    def test_check_api_availability(self):
        """API キーが設定されているか確認"""
        # 本実装の場合、環境変数次第で True/False が返る
        result = LLMService.check_api_availability()
        assert isinstance(result, bool)
    
    @patch('app.services.llm_service.genai.GenerativeModel')
    def test_analyze_creative_success(self, mock_genai):
        """正常な Gemini レスポンス処理"""
        # モック レスポンス
        mock_response = MagicMock()
        mock_response.text = """{
            "visuals": {
                "dominant_colors": ["blue", "white"],
                "composition": "centered",
                "style": "modern",
                "clarity": "high"
            },
            "tone": {
                "primary_tone": ["professional", "trustworthy"],
                "emotional_appeal": "logical",
                "call_to_action": "strong"
            },
            "ai_labels": ["finance", "trust", "innovation"]
        }"""
        
        mock_genai.return_value.generate_content.return_value = mock_response
        
        result = LLMService.analyze_creative(
            image_description="A blue and white financial app interface",
            lp_content="Secure your future with our investment platform"
        )
        
        assert "visuals" in result
        assert "tone" in result
        assert "ai_labels" in result
        assert isinstance(result["ai_labels"], list)
    
    @patch('app.services.llm_service.genai.GenerativeModel')
    def test_analyze_creative_with_json_block(self, mock_genai):
        """```json ... ``` ブロック形式のレスポンス処理"""
        mock_response = MagicMock()
        mock_response.text = """分析結果は以下の通りです：
```json
{
    "visuals": {"dominant_colors": ["red"], "composition": "left-aligned", "style": "bold", "clarity": "medium"},
    "tone": {"primary_tone": ["energetic"], "emotional_appeal": "emotional", "call_to_action": "medium"},
    "ai_labels": ["sports", "energy"]
}
```
"""

        mock_genai.return_value.generate_content.return_value = mock_response
        
        result = LLMService.analyze_creative(image_description="Sports ad")
        
        assert result["visuals"]["dominant_colors"] == ["red"]
        assert result["ai_labels"] == ["sports", "energy"]

    @patch('app.services.llm_service.genai.GenerativeModel')
    def test_analyze_creative_invalid_json(self, mock_genai):
        """不正な JSON レスポンスの処理"""
        mock_response = MagicMock()
        mock_response.text = "This is not JSON"
        
        mock_genai.return_value.generate_content.return_value = mock_response
        
        with pytest.raises(ValueError, match="Failed to parse Gemini response as JSON"):
            LLMService.analyze_creative(image_description="Test")

    @patch('app.services.llm_service.GEMINI_API_KEY', None)
    def test_analyze_creative_no_api_key(self):
        """API キーが未設定の場合"""
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
            LLMService.analyze_creative(image_description="Test")
