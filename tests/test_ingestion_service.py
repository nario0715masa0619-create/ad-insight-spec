"""
Tests for IngestionService

Test coverage:
- Video file ingestion (MP4)
- Image file ingestion (PNG, JPG)
- Text file ingestion (TXT)
- Error handling (file not found, unsupported format, corrupted file)
- Format detection
"""

import pytest
import tempfile
import os
from pathlib import Path

from app.services.ingestion_service import IngestionService, IngestedAsset
from app.services.base_service import ValidationError, ProcessingError


class TestIngestionService:
    """Test suite for IngestionService"""
    
    @pytest.fixture
    def service(self):
        """Create IngestionService instance"""
        return IngestionService()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    # ===== Format Detection Tests =====
    
    def test_detect_video_format_mp4(self, service):
        """Test detection of MP4 format"""
        assert service.detect_format("test.mp4") == "video_static"
    
    def test_detect_video_format_mov(self, service):
        """Test detection of MOV format"""
        assert service.detect_format("test.mov") == "video_static"
    
    def test_detect_image_format_png(self, service):
        """Test detection of PNG format"""
        assert service.detect_format("test.png") == "image_static"
    
    def test_detect_image_format_jpg(self, service):
        """Test detection of JPG format"""
        assert service.detect_format("test.jpg") == "image_static"
    
    def test_detect_text_format_txt(self, service):
        """Test detection of TXT format"""
        assert service.detect_format("test.txt") == "text_only"
    
    def test_detect_text_format_md(self, service):
        """Test detection of MD format"""
        assert service.detect_format("test.md") == "text_only"
    
    def test_detect_unsupported_format(self, service):
        """Test detection of unsupported format"""
        with pytest.raises(ValidationError):
            service.detect_format("test.docx")
    
    def test_detect_format_case_insensitive(self, service):
        """Test that format detection is case-insensitive"""
        assert service.detect_format("test.MP4") == "video_static"
        assert service.detect_format("test.PNG") == "image_static"
        assert service.detect_format("test.TXT") == "text_only"
    
    # ===== File Validation Tests =====
    
    def test_validate_file_exists_true(self, service, temp_dir):
        """Test validation of existing file"""
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        
        assert service.validate_file_exists(test_file) is True
    
    def test_validate_file_not_found(self, service):
        """Test validation of non-existent file"""
        with pytest.raises(ValidationError):
            service.validate_file_exists("/nonexistent/file.txt")
    
    def test_validate_directory_not_file(self, service, temp_dir):
        """Test that directories are rejected"""
        with pytest.raises(ValidationError):
            service.validate_file_exists(temp_dir)
    
    # ===== Text File Ingestion Tests =====
    
    def test_ingest_text_utf8(self, service, temp_dir):
        """Test ingestion of UTF-8 text file"""
        test_file = os.path.join(temp_dir, "test.txt")
        test_content = "Hello, World! これはテストです。"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        result = service.execute(test_file)
        
        assert result["format"] == "text_only"
        assert result["data"] == test_content
        assert result["metadata"]["char_count"] == len(test_content)
        assert result["metadata"]["line_count"] == 1
        assert result["metadata"]["encoding"] == "utf-8"
    
    def test_ingest_text_multiline(self, service, temp_dir):
        """Test ingestion of multiline text file"""
        test_file = os.path.join(temp_dir, "test.txt")
        test_content = "Line 1\nLine 2\nLine 3"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        result = service.execute(test_file)
        
        assert result["data"] == test_content
        assert result["metadata"]["line_count"] == 3
    
    def test_ingest_text_sjis(self, service, temp_dir):
        """Test ingestion of Shift-JIS encoded text"""
        test_file = os.path.join(temp_dir, "test.txt")
        test_content = "日本語テスト"
        
        with open(test_file, 'w', encoding='shift_jis') as f:
            f.write(test_content)
        
        result = service.execute(test_file)
        
        assert result["format"] == "text_only"
        assert result["data"] == test_content
        assert result["metadata"]["encoding"] == "shift_jis"
    
    def test_ingest_markdown(self, service, temp_dir):
        """Test ingestion of Markdown file"""
        test_file = os.path.join(temp_dir, "test.md")
        test_content = "# Title\n\nSome content"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        result = service.execute(test_file)
        
        assert result["format"] == "text_only"
        assert result["metadata"]["extension"] == ".md"
    
    def test_ingest_empty_text_file(self, service, temp_dir):
        """Test that empty text files are rejected"""
        test_file = os.path.join(temp_dir, "empty.txt")
        with open(test_file, 'w') as f:
            pass  # Create empty file
        
        with pytest.raises(ProcessingError):
            service.execute(test_file)
    
    # ===== Image File Ingestion Tests =====
    
    def test_ingest_png_file(self, service, temp_dir):
        """Test ingestion of PNG file"""
        test_file = os.path.join(temp_dir, "test.png")
        
        # Create minimal valid PNG
        png_header = b'\x89PNG\r\n\x1a\n'
        with open(test_file, 'wb') as f:
            f.write(png_header)
            f.write(b'\x00' * 100)  # Dummy data
        
        result = service.execute(test_file)
        
        assert result["format"] == "image_static"
        assert isinstance(result["data"], bytes)
        assert len(result["data"]) > 0
        assert result["metadata"]["extension"] == ".png"
    
    def test_ingest_jpeg_file(self, service, temp_dir):
        """Test ingestion of JPEG file"""
        test_file = os.path.join(temp_dir, "test.jpg")
        
        # Create minimal valid JPEG
        jpeg_header = b'\xff\xd8\xff'
        with open(test_file, 'wb') as f:
            f.write(jpeg_header)
            f.write(b'\x00' * 100)  # Dummy data
        
        result = service.execute(test_file)
        
        assert result["format"] == "image_static"
        assert result["metadata"]["extension"] == ".jpg"
    
    def test_ingest_empty_image_file(self, service, temp_dir):
        """Test that empty image files are rejected"""
        test_file = os.path.join(temp_dir, "empty.png")
        with open(test_file, 'wb') as f:
            pass  # Create empty file
        
        with pytest.raises(ProcessingError):
            service.execute(test_file)
    
    # ===== Video File Ingestion Tests =====
    
    def test_ingest_video_file_basic(self, service, temp_dir):
        """Test basic video file ingestion"""
        test_file = os.path.join(temp_dir, "test.mp4")
        
        # Create minimal file with MP4 signature
        with open(test_file, 'wb') as f:
            f.write(b'\x00\x00\x00\x20ftypisom')  # MP4 header
            f.write(b'\x00' * 1000)  # Dummy data
        
        result = service.execute(test_file)
        
        assert result["format"] == "video_static"
        assert isinstance(result["data"], bytes)
        assert len(result["data"]) > 0
        assert result["metadata"]["extension"] == ".mp4"
    
    def test_ingest_empty_video_file(self, service, temp_dir):
        """Test that empty video files are rejected"""
        test_file = os.path.join(temp_dir, "empty.mp4")
        with open(test_file, 'wb') as f:
            pass  # Create empty file
        
        with pytest.raises(ProcessingError):
            service.execute(test_file)
    
    # ===== Metadata Tests =====
    
    def test_metadata_includes_file_path(self, service, temp_dir):
        """Test that metadata includes file path"""
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        
        result = service.execute(test_file)
        
        assert "file_path" in result["metadata"]
        assert result["metadata"]["file_path"] == str(Path(test_file).absolute())
    
    def test_metadata_includes_file_name(self, service, temp_dir):
        """Test that metadata includes file name"""
        test_file = os.path.join(temp_dir, "test_file.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        
        result = service.execute(test_file)
        
        assert result["metadata"]["file_name"] == "test_file.txt"
    
    def test_metadata_includes_file_size(self, service, temp_dir):
        """Test that metadata includes file size"""
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        
        result = service.execute(test_file)
        
        assert "file_size_bytes" in result["metadata"]
        assert result["metadata"]["file_size_bytes"] > 0
    
    # ===== Error Handling Tests =====
    
    def test_execute_file_not_found(self, service):
        """Test execute with non-existent file"""
        with pytest.raises(ValidationError):
            service.execute("/nonexistent/file.txt")
    
    def test_execute_unsupported_format(self, service, temp_dir):
        """Test execute with unsupported format"""
        test_file = os.path.join(temp_dir, "test.docx")
        with open(test_file, 'w') as f:
            f.write("test")
        
        with pytest.raises(ValidationError):
            service.execute(test_file)


class TestIngestedAsset:
    """Test suite for IngestedAsset data class"""
    
    def test_ingested_asset_to_dict(self):
        """Test conversion of IngestedAsset to dict"""
        asset = IngestedAsset(
            format="text_only",
            data="test content",
            metadata={"key": "value"},
            file_path="/path/to/file.txt"
        )
        
        result = asset.to_dict()
        
        assert result["format"] == "text_only"
        assert result["data"] == "test content"
        assert result["metadata"] == {"key": "value"}
        assert result["file_path"] == "/path/to/file.txt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
