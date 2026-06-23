"""
Tests for VideoService

Test coverage:
- Video metadata extraction
- Frame extraction from video
- Input validation (video format, file existence)
- Error handling (invalid paths, unsupported formats)
- Metadata parsing (duration, resolution, fps)

Note: Tests use minimal dummy MP4 files created in temp directory.
"""

import pytest
import tempfile
from pathlib import Path
import struct

from app.services.video_service import VideoService
from app.services.base_service import ValidationError, ProcessingError


class TestVideoService:
    """Test suite for VideoService"""
    
    @pytest.fixture
    def service(self):
        """Create VideoService instance"""
        return VideoService(num_frames=3)
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def dummy_mp4_file(self, temp_dir):
        """Create a minimal dummy MP4 file for testing"""
        mp4_path = Path(temp_dir) / "test.mp4"
        
        # Create minimal MP4 header (ftyp + mdat boxes)
        with open(mp4_path, 'wb') as f:
            # ftyp box (minimal)
            ftyp = b'\x00\x00\x00\x20ftypisom\x00\x00\x00\x00isomiso2mp41'
            f.write(ftyp)
            
            # mdat box with dummy video data
            mdat_size = 10000
            mdat_header = struct.pack('>I', mdat_size) + b'mdat'
            f.write(mdat_header)
            f.write(b'\x00' * (mdat_size - 8))
        
        return str(mp4_path)
    
    # ===== Input Validation Tests =====
    
    def test_validate_input_valid_mp4(self, service, dummy_mp4_file):
        """Test validation of valid MP4 file"""
        assert service.validate_input(dummy_mp4_file) is True
    
    def test_validate_input_file_not_found(self, service):
        """Test validation rejects non-existent file"""
        with pytest.raises(ValidationError):
            service.validate_input("/nonexistent/video.mp4")
    
    def test_validate_input_unsupported_format(self, service, temp_dir):
        """Test validation rejects unsupported format"""
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("not a video")
        
        with pytest.raises(ValidationError):
            service.validate_input(str(test_file))
    
    def test_validate_input_not_string(self, service):
        """Test validation rejects non-string input"""
        with pytest.raises(ValidationError):
            service.validate_input(123)
    
    def test_validate_input_directory(self, service, temp_dir):
        """Test validation rejects directory"""
        with pytest.raises(ValidationError):
            service.validate_input(temp_dir)
    
    # ===== Metadata Tests =====
    
    def test_parse_fps_simple_format(self, service):
        """Test FPS parsing from simple format"""
        assert service._parse_fps("30") == 30.0
    
    def test_parse_fps_fraction_format(self, service):
        """Test FPS parsing from fraction format (e.g., 24/1)"""
        assert service._parse_fps("24/1") == 24.0
    
    def test_parse_fps_complex_format(self, service):
        """Test FPS parsing from complex format (e.g., 30000/1001)"""
        fps = service._parse_fps("30000/1001")
        assert abs(fps - 29.97) < 0.01
    
    def test_parse_fps_invalid_format(self, service):
        """Test FPS parsing with invalid format returns default"""
        result = service._parse_fps("invalid")
        assert result == 30.0  # Default
    
    # ===== Fallback Metadata Tests =====
    
    def test_get_fallback_metadata_structure(self, service):
        """Test fallback metadata has required fields"""
        metadata = service._get_fallback_metadata("")  # Won't actually be used
        
        assert "duration" in metadata
        assert "resolution" in metadata
        assert "fps" in metadata
        assert "codec" in metadata
        assert "bitrate" in metadata
    
    # ===== Execute Tests (with dummy file) =====
    
    def test_execute_returns_required_fields(self, service, dummy_mp4_file):
        """Test that execute returns all required output fields"""
        # Skip if FFmpeg not available
        try:
            import subprocess
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except:
            pytest.skip("FFmpeg not available")
        
        result = service.execute(dummy_mp4_file)
        
        assert "duration_seconds" in result
        assert "resolution" in result
        assert "fps" in result
        assert "frame_count_estimate" in result
        assert "sampled_frames" in result
        assert "thumbnail_path" in result
        assert "extraction_metadata" in result
        assert "success" in result
        assert "message" in result
    
    def test_execute_success_status(self, service, dummy_mp4_file):
        """Test that execute returns success status"""
        try:
            import subprocess
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except:
            pytest.skip("FFmpeg not available")
        
        result = service.execute(dummy_mp4_file)
        assert result["success"] is True
    
    def test_execute_frame_count_estimate(self, service, dummy_mp4_file):
        """Test frame count estimation"""
        try:
            import subprocess
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except:
            pytest.skip("FFmpeg not available")
        
        result = service.execute(dummy_mp4_file)
        
        # frame_count_estimate = duration * fps
        assert result["frame_count_estimate"] >= 0
    
    # ===== Error Handling Tests =====
    
    def test_execute_invalid_file(self, service):
        """Test execute with invalid file"""
        with pytest.raises(ValidationError):
            service.execute("/nonexistent/video.mp4")
    
    def test_execute_unsupported_format(self, service, temp_dir):
        """Test execute with unsupported format"""
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("not a video")
        
        with pytest.raises(ValidationError):
            service.execute(str(test_file))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
