import pytesseract
from pytesseract import Output
from PIL import Image
import cv2
import numpy as np
from typing import Optional, List, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

if os.name == 'nt':
    tesseract_path = os.environ.get("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

class OCRService:
    """Tesseract を使用した OCR サービス"""
    
    # 動画フレーム抽出設定
    VIDEO_FRAME_INDICES = [0.0, 0.5, 1.0]  # 先頭、中盤、末尾（相対位置）
    
    @staticmethod
    def extract_text_from_image(file_path: str) -> Dict[str, Any]:
        """
        画像から文字を抽出
        
        Args:
            file_path: 画像ファイルパス
        
        Returns:
            {
                "success": bool,
                "ocr_extracted_text": str,
                "confidence": float,
                "raw_data": dict or None
            }
        """
        try:
            image = Image.open(file_path)
            
            # Tesseract で OCR 実行
            text = pytesseract.image_to_string(image, lang='eng+jpn')
            
            # 信頼度情報を取得
            data = pytesseract.image_to_data(image, output_type=Output.DICT, lang='eng+jpn')
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            # テキストをクリーニング
            cleaned_text = text.strip()
            
            return {
                "success": bool(cleaned_text),
                "ocr_extracted_text": cleaned_text,
                "confidence": round(avg_confidence / 100, 2),
                "raw_data": {
                    "num_words": len(cleaned_text.split()),
                    "num_lines": len(cleaned_text.split('\n')),
                    "avg_confidence": round(avg_confidence, 1)
                } if cleaned_text else None
            }
            
        except Exception as e:
            logger.error(f"OCR error on image {file_path}: {str(e)}")
            return {
                "success": False,
                "ocr_extracted_text": "",
                "confidence": 0.0,
                "raw_data": None
            }
    
    @staticmethod
    def extract_frames_from_video(file_path: str) -> List[Dict[str, Any]]:
        """
        動画から指定フレーム（先頭・中盤・末尾）を抽出
        
        Args:
            file_path: 動画ファイルパス
        
        Returns:
            [
                {
                    "frame_index": int,
                    "relative_position": float,
                    "ocr_extracted_text": str,
                    "confidence": float
                },
                ...
            ]
        """
        try:
            cap = cv2.VideoCapture(file_path)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if frame_count == 0:
                logger.warning(f"No frames in video {file_path}")
                return []
            
            frames_data = []
            
            for relative_pos in OCRService.VIDEO_FRAME_INDICES:
                frame_idx = int(relative_pos * (frame_count - 1))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"Failed to read frame {frame_idx}")
                    continue
                
                # フレームを RGB に変換
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_pil = Image.fromarray(frame_rgb)
                
                # OCR 実行
                text = pytesseract.image_to_string(frame_pil, lang='eng+jpn')
                data = pytesseract.image_to_data(frame_pil, output_type=Output.DICT, lang='eng+jpn')
                confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                cleaned_text = text.strip()
                
                frames_data.append({
                    "frame_index": frame_idx,
                    "relative_position": relative_pos,
                    "ocr_extracted_text": cleaned_text,
                    "confidence": round(avg_confidence / 100, 2)
                })
            
            cap.release()
            return frames_data
            
        except Exception as e:
            logger.error(f"Video OCR error on {file_path}: {str(e)}")
            return []
    
    @staticmethod
    def extract_text_from_video(file_path: str) -> Dict[str, Any]:
        """
        動画フレームの OCR 結果をマージ
        
        Args:
            file_path: 動画ファイルパス
        
        Returns:
            {
                "success": bool,
                "ocr_extracted_text": str (改行でマージ),
                "frames": [...],
                "confidence": float (平均)
            }
        """
        frames_data = OCRService.extract_frames_from_video(file_path)
        
        if not frames_data:
            return {
                "success": False,
                "ocr_extracted_text": "",
                "frames": [],
                "confidence": 0.0
            }
        
        # フレーム結果を改行で結合（重複排除）
        unique_texts = []
        for frame in frames_data:
            text = frame["ocr_extracted_text"].strip()
            if text and text not in unique_texts:
                unique_texts.append(text)
        
        merged_text = "\n".join(unique_texts)
        avg_confidence = sum(f["confidence"] for f in frames_data) / len(frames_data)
        
        return {
            "success": bool(merged_text),
            "ocr_extracted_text": merged_text,
            "frames": frames_data,
            "confidence": round(avg_confidence, 2)
        }
    
    @staticmethod
    def extract_text(file_path: str, media_type: str = "image") -> Dict[str, Any]:
        """
        統一インターフェース：画像または動画から文字を抽出
        
        Args:
            file_path: メディアファイルパス
            media_type: "image" または "video"
        
        Returns:
            構造化 OCR 結果（失敗時も ocr_extracted_text: "" で返却）
        """
        if media_type == "video":
            return OCRService.extract_text_from_video(file_path)
        else:
            return OCRService.extract_text_from_image(file_path)
