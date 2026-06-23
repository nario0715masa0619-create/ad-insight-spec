"""
Tests for MetadataService

Test coverage:
- asset_id generation (format validation)
- Text metadata extraction (char_count, line_count, language detection)
- Image metadata extraction (resolution from PNG)
- Video metadata extraction (file size estimation)
- Language detection (Japanese, English)
- Input validation
- Error handling
"""

import pytest
from datetime import datetime

from app.services.metadata_service import MetadataService, MockIngestedAsset
from app.services.base_service import ValidationError, ProcessingError


class TestMetadataService:
    """Test suite for MetadataService"""
    
    @pytest.fixture
    def service(self):
        """Create MetadataService instance"""
        return MetadataService()
    
    # ===== Asset ID Generation Tests =====
    
    def test_generate_asset_id_format(self, service):
        """Test asset_id format: asset_YYYYMMDD_HHmmss_local_<uuid>"""
        asset_id = service._generate_asset_id()
        
        # Format check
        parts = asset_id.split('_')
        assert len(parts) == 5
        assert parts[0] == "asset"
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHmmss
        assert parts[3] == "local"
        assert len(parts[4]) == 8  # UUID (shortened)
    
    def test_generate_asset_id_uniqueness(self, service):
        """Test that generated asset_ids are unique"""
        ids = [service._generate_asset_id() for _ in range(10)]
        assert len(ids) == len(set(ids)), "Generated IDs should be unique"
    
    def test_generate_asset_id_date_format(self, service):
        """Test that generated asset_id contains valid date"""
        asset_id = service._generate_asset_id()
        date_part = asset_id.split('_')[1]
        
        # Should be parseable as YYYYMMDD
        try:
            datetime.strptime(date_part, "%Y%m%d")
        except ValueError:
            pytest.fail(f"Invalid date format in asset_id: {date_part}")
    
    # ===== Input Validation Tests =====
    
    def test_validate_input_valid_asset(self, service):
        """Test validation of valid ingested asset"""
        asset = MockIngestedAsset.create_text_asset("test content")
        assert service.validate_input(asset) is True
    
    def test_validate_input_missing_format(self, service):
        """Test validation fails when format is missing"""
        asset = {
            "data": b"test",
            "metadata": {},
            "file_path": "/tmp/test"
        }
        with pytest.raises(ValidationError):
            service.validate_input(asset)
    
    def test_validate_input_missing_data(self, service):
        """Test validation fails when data is missing"""
        asset = {
            "format": "text_only",
            "metadata": {},
            "file_path": "/tmp/test"
        }
        with pytest.raises(ValidationError):
            service.validate_input(asset)
    
    def test_validate_input_invalid_format(self, service):
        """Test validation fails with invalid format"""
        asset = {
            "format": "invalid_format",
            "data": b"test",
            "metadata": {},
            "file_path": "/tmp/test"
        }
        with pytest.raises(ValidationError):
            service.validate_input(asset)
    
    def test_validate_input_not_dict(self, service):
        """Test validation fails when input is not dict"""
        with pytest.raises(ValidationError):
            service.validate_input("not a dict")
    
    # ===== Text Metadata Extraction Tests =====
    
    def test_extract_text_metadata_char_count(self, service):
        """Test char_count in text metadata"""
        asset = MockIngestedAsset.create_text_asset("Hello, World!")
        result = service.execute(asset)
        
        assert result["char_count"] == 13
    
    def test_extract_text_metadata_line_count(self, service):
        """Test line_count in text metadata"""
        asset = MockIngestedAsset.create_text_asset("Line 1\nLine 2\nLine 3")
        result = service.execute(asset)
        
        assert result["line_count"] == 3
    
    def test_extract_text_metadata_word_count(self, service):
        """Test word_count in text metadata"""
        asset = MockIngestedAsset.create_text_asset("The quick brown fox")
        result = service.execute(asset)
        
        assert result["word_count"] == 4
    
    def test_extract_text_metadata_japanese_language_detection(self, service):
        """Test language detection for Japanese text"""
        asset = MockIngestedAsset.create_text_asset("これはテストです")
        result = service.execute(asset)
        
        assert result["language"] == "ja"
    
    def test_extract_text_metadata_english_language_detection(self, service):
        """Test language detection for English text"""
        asset = MockIngestedAsset.create_text_asset("This is a test")
        result = service.execute(asset)
        
        assert result["language"] == "en"
    
    def test_extract_text_metadata_mixed_language_detection(self, service):
        """Test language detection for mixed JP-EN text (prefers JP)"""
        asset = MockIngestedAsset.create_text_asset("This is テスト mixed content")
        result = service.execute(asset)
        
        assert result["language"] == "ja"
    
    def test_extract_text_metadata_encoding(self, service):
        """Test encoding information in metadata"""
        asset = MockIngestedAsset.create_text_asset("test", encoding="utf-8")
        result = service.execute(asset)
        
        assert result["encoding"] == "utf-8"
    
    def test_extract_text_metadata_mime_type(self, service):
        """Test MIME type for text files"""
        asset = MockIngestedAsset.create_text_asset("test")
        result = service.execute(asset)
        
        assert result["mime_type"] == "text/plain"
    
    def test_extract_text_metadata_markdown_mime_type(self, service):
        """Test MIME type for Markdown files"""
        asset = {
            "format": "text_only",
            "data": "# Title\n\nContent",
            "metadata": {
                "file_path": "/tmp/test.md",
                "file_name": "test.md",
                "file_size_bytes": 20,
                "extension": ".md",
                "encoding": "utf-8",
                "char_count": 20,
                "line_count": 3,
                "file_exists": True,
                "is_readable": True,
            },
            "file_path": "/tmp/test.md"
        }
        result = service.execute(asset)
        
        assert result["mime_type"] == "text/markdown"
    
    # ===== Image Metadata Extraction Tests =====
    
    def test_extract_image_metadata_mime_type_png(self, service):
        """Test MIME type for PNG files"""
        asset = MockIngestedAsset.create_image_asset()
        result = service.execute(asset)
        
        assert result["mime_type"] == "image/png"
    
    def test_extract_image_metadata_resolution_from_png(self, service):
        """Test resolution extraction from PNG header"""
        asset = MockIngestedAsset.create_image_asset()
        result = service.execute(asset)
        
        # PNG header contains 640x480
        assert result["width_pixels"] == 640
        assert result["height_pixels"] == 480
    
    def test_extract_image_metadata_color_space_png(self, service):
        """Test color space for PNG"""
        asset = MockIngestedAsset.create_image_asset()
        result = service.execute(asset)
        
        assert result["color_space"] == "RGBA"
    
    # ===== Video Metadata Extraction Tests =====
    
    def test_extract_video_metadata_mime_type(self, service):
        """Test MIME type for video files"""
        asset = MockIngestedAsset.create_video_asset()
        result = service.execute(asset)
        
        assert result["mime_type"] == "video/mp4"
    
    def test_extract_video_metadata_file_size_estimation(self, service):
        """Test bit rate estimation from file size"""
        size = 5 * 1024 * 1024  # 5 MB
        asset = MockIngestedAsset.create_video_asset(size=size)
        result = service.execute(asset)
        
        # Should have bit_rate estimation
        assert result["bit_rate"] is not None
        assert result["bit_rate"] > 0
    
    # ===== General Metadata Tests =====
    
    def test_execute_returns_asset_id(self, service):
        """Test that execute returns asset_id"""
        asset = MockIngestedAsset.create_text_asset("test")
        result = service.execute(asset)
        
        assert "asset_id" in result
        assert result["asset_id"].startswith("asset_")
    
    def test_execute_returns_format(self, service):
        """Test that execute returns format"""
        asset = MockIngestedAsset.create_text_asset("test")
        result = service.execute(asset)
        
        assert result["format"] == "text_only"
    
    def test_execute_returns_extracted_timestamp(self, service):
        """Test that execute includes extraction timestamp"""
        asset = MockIngestedAsset.create_text_asset("test")
        result = service.execute(asset)
        
        assert "extracted_at" in result
        # Should be ISO format with Z suffix
        assert result["extracted_at"].endswith("Z")
    
    def test_execute_preserves_base_metadata(self, service):
        """Test that execute preserves base metadata from ingestion"""
        asset = MockIngestedAsset.create_text_asset("test")
        result = service.execute(asset)
        
        assert result["file_path"] == "/tmp/test.txt"
        assert result["file_name"] == "test.txt"
        assert result["extension"] == ".txt"
    
    # ===== Error Handling Tests =====
    
    def test_execute_invalid_asset_structure(self, service):
        """Test execute with invalid asset structure"""
        with pytest.raises(ValidationError):
            service.execute({"invalid": "structure"})
    
    def test_execute_unknown_format(self, service):
        """Test execute with unknown format"""
        asset = {
            "format": "unknown_format",
            "data": b"test",
            "metadata": {"file_path": "/tmp/test"},
            "file_path": "/tmp/test"
        }
        with pytest.raises(ValidationError):
            service.execute(asset)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
