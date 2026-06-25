import pytest
import os
from PIL import Image
import cv2
import numpy as np
from app.services.ocr_service import OCRService

class TestOCRServiceImage:
    """画像 OCR テスト"""
    
    @pytest.fixture
    def test_image_with_text(self, tmp_path):
        """テキスト入り画像を生成"""
        img = Image.new('RGB', (400, 200), color='white')
        # PIL で直接テキストを描画（簡易版）
        # 実際には以下のような画像が必要
        test_file = tmp_path / "test_with_text.png"
        img.save(test_file)
        return str(test_file)
    
    def test_extract_text_from_image_success(self, test_image_with_text):
        """画像テキスト抽出成功"""
        result = OCRService.extract_text_from_image(test_image_with_text)
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "ocr_extracted_text" in result
        assert "confidence" in result
        assert isinstance(result["ocr_extracted_text"], str)
        assert isinstance(result["confidence"], float)
    
    def test_extract_text_from_image_no_text(self, tmp_path):
        """テキストなし画像（Fail-Soft）"""
        # 無地画像
        img = Image.new('RGB', (200, 200), color='white')
        test_file = tmp_path / "blank.png"
        img.save(test_file)
        
        result = OCRService.extract_text_from_image(str(test_file))
        
        assert result["success"] is False
        assert result["ocr_extracted_text"] == ""
        assert result["confidence"] == 0.0
    
    def test_extract_text_from_image_not_found(self):
        """ファイル未検出（Fail-Soft）"""
        result = OCRService.extract_text_from_image("/nonexistent/image.png")
        
        assert result["success"] is False
        assert result["ocr_extracted_text"] == ""
        assert result["confidence"] == 0.0


class TestOCRServiceVideo:
    """動画 OCR テスト"""
    
    @pytest.fixture
    def test_video(self, tmp_path):
        """簡単な動画ファイルを生成"""
        video_file = tmp_path / "test.mp4"
        
        # OpenCV で簡単なビデオを生成
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(video_file), fourcc, 10.0, (400, 300))
        
        for i in range(30):  # 30 フレーム、10fps なら 3 秒
            frame = np.zeros((300, 400, 3), dtype=np.uint8)
            cv2.putText(frame, "Test Video", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            out.write(frame)
        
        out.release()
        return str(video_file)
    
    def test_extract_frames_from_video(self, test_video):
        """動画フレーム抽出（3 フレーム）"""
        frames = OCRService.extract_frames_from_video(test_video)
        
        assert isinstance(frames, list)
        assert len(frames) <= 3  # 最大 3 フレーム
        
        for frame in frames:
            assert "frame_index" in frame
            assert "relative_position" in frame
            assert "ocr_extracted_text" in frame
            assert "confidence" in frame
    
    def test_extract_text_from_video_success(self, test_video):
        """動画 OCR（マージ）成功"""
        result = OCRService.extract_text_from_video(test_video)
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "ocr_extracted_text" in result
        assert "frames" in result
        assert "confidence" in result
        assert isinstance(result["frames"], list)
    
    def test_extract_text_from_video_not_found(self):
        """動画未検出（Fail-Soft）"""
        result = OCRService.extract_text_from_video("/nonexistent/video.mp4")
        
        assert result["success"] is False
        assert result["ocr_extracted_text"] == ""
        assert result["frames"] == []
        assert result["confidence"] == 0.0


class TestOCRServiceIntegration:
    """統一インターフェース テスト"""
    
    def test_extract_text_image_interface(self, tmp_path):
        """統一インターフェース（画像）"""
        img = Image.new('RGB', (200, 200), color='white')
        test_file = tmp_path / "test.png"
        img.save(test_file)
        
        result = OCRService.extract_text(str(test_file), media_type="image")
        
        assert "ocr_extracted_text" in result
        assert isinstance(result["ocr_extracted_text"], str)
    
    def test_extract_text_video_interface(self, tmp_path):
        """統一インターフェース（動画）"""
        # 簡単なビデオを生成
        video_file = tmp_path / "test.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(video_file), fourcc, 10.0, (200, 200))
        
        for i in range(10):
            frame = np.zeros((200, 200, 3), dtype=np.uint8)
            out.write(frame)
        
        out.release()
        
        result = OCRService.extract_text(str(video_file), media_type="video")
        
        assert "ocr_extracted_text" in result
        assert "frames" in result
        assert isinstance(result["frames"], list)
