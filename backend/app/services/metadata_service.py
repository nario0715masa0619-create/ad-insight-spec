"""
MetadataService - Extract and generate metadata

Responsibilities:
- Generate unique asset_id (asset_YYYYMMDD_HHmmss_local_uuid)
- Extract video metadata (duration, resolution, fps, codec)
- Extract image metadata (width, height, color_space)
- Extract text metadata (char_count, line_count, language)
- Return metadata dict for asset_meta section

Input: IngestedAsset dict (from IngestionService)
Output: metadata dict for asset_meta population
"""

import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import logging
import json

from app.services.base_service import BaseService, ValidationError, ProcessingError


logger = logging.getLogger(__name__)


class MetadataService(BaseService):
    """
    Service for extracting and generating metadata from ingested assets.
    
    Generates:
    - asset_id: Unique identifier
    - Basic metadata: file size, extension, etc.
    - Format-specific metadata: duration (video), resolution (image), encoding (text)
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def execute(self, ingested_asset: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from ingested asset.
        
        Args:
            ingested_asset (dict): Output from IngestionService
                {
                    "format": "video_static" | "image_static" | "text_only",
                    "data": <bytes or str>,
                    "metadata": {...},
                    "file_path": str
                }
        
        Returns:
            dict: Metadata for asset_meta section
                {
                    "asset_id": "asset_20260623_143000_local_xyz",
                    "duration_seconds": <float or null>,
                    "resolution": "1920x1080" or null,
                    "fps": <float or null>,
                    "codec": <str or null>,
                    ...
                }
        
        Raises:
            ValidationError: Invalid ingested asset
            ProcessingError: Metadata extraction failed
        """
        self.validate_input(ingested_asset)
        
        try:
            asset_format = ingested_asset["format"]
            data = ingested_asset["data"]
            metadata = ingested_asset["metadata"]
            
            self.logger.info(f"Extracting metadata for format: {asset_format}")
            
            # Generate asset_id
            platform = metadata.get("platform", "unknown")
            content_bytes = data.encode('utf-8') if isinstance(data, str) else data
            asset_id = self._generate_asset_id(platform=platform, file_content=content_bytes)
            self.logger.info(f"Generated asset_id: {asset_id}")
            
            # Extract format-specific metadata
            if asset_format == "video_static":
                format_metadata = self._extract_video_metadata(data, metadata)
            elif asset_format == "image_static":
                format_metadata = self._extract_image_metadata(data, metadata)
            elif asset_format == "text_only":
                format_metadata = self._extract_text_metadata(data, metadata)
            else:
                raise ValidationError(f"Unknown format: {asset_format}")
            
            # Merge all metadata
            result = {
                "asset_id": asset_id,
                "format": asset_format,
                "extracted_at": datetime.now().isoformat() + "Z",
                **metadata,
                **format_metadata
            }
            
            self.logger.info(f"Metadata extraction successful")
            return result
        
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to extract metadata: {str(e)}")
    
    def validate_input(self, ingested_asset: Dict[str, Any]) -> bool:
        """
        Validate ingested asset structure.
        
        Args:
            ingested_asset (dict): Asset from IngestionService
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If invalid
        """
        if not isinstance(ingested_asset, dict):
            raise ValidationError(f"ingested_asset must be dict, got {type(ingested_asset)}")
        
        required_keys = ["format", "data", "metadata", "file_path"]
        for key in required_keys:
            if key not in ingested_asset:
                raise ValidationError(f"ingested_asset missing required key: {key}")
        
        valid_formats = ["video_static", "image_static", "text_only"]
        if ingested_asset["format"] not in valid_formats:
            raise ValidationError(f"Invalid format: {ingested_asset['format']}")
        
        return True
    
    def _generate_asset_id(self, platform: str, file_content: bytes) -> str:
        """
        Generate unique asset ID based on content hash.
        Format: asset_<platform>_<sha256_hash_first_16_chars>
        
        Example: asset_unknown_a1b2c3d4e5f6g7h8
        
        Returns:
            str: Unique asset ID
        """
        content_hash = hashlib.sha256(file_content).hexdigest()[:16]
        asset_id = f"asset_{platform}_{content_hash}"
        return asset_id
    
    def _extract_video_metadata(self, data: bytes, base_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract video metadata.
        
        Uses simple heuristics without external libraries (FFmpeg will be called later).
        
        Args:
            data (bytes): Video file content
            base_metadata (dict): Basic metadata from IngestionService
        
        Returns:
            dict: Video-specific metadata
                {
                    "duration_seconds": <float or null>,
                    "resolution": "1920x1080" or null,
                    "fps": <float or null>,
                    "codec": <str or null>,
                    "bit_rate": <int or null>,
                    "mime_type": "video/mp4"
                }
        """
        result = {
            "duration_seconds": None,
            "resolution": None,
            "fps": None,
            "codec": None,
            "bit_rate": None,
            "mime_type": "video/mp4",
        }
        
        # Try to extract from metadata dict if present
        if "duration_seconds" in base_metadata:
            result["duration_seconds"] = base_metadata["duration_seconds"]
        
        # File size estimation for bitrate (rough heuristic)
        if "file_size_bytes" in base_metadata:
            file_size_mb = base_metadata["file_size_bytes"] / (1024 * 1024)
            # Assume 5 minutes average, rough calculation
            if file_size_mb > 0:
                result["bit_rate"] = int((file_size_mb * 8) / 5)  # kbps approximation
        
        # Determine MIME type based on extension
        extension = base_metadata.get("extension", "").lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
        }
        result["mime_type"] = mime_map.get(extension, "video/mp4")
        
        self.logger.info(f"Video metadata extracted: {result}")
        return result
    
    def _extract_image_metadata(self, data: bytes, base_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract image metadata without PIL (will be used by Vision API later).
        
        Args:
            data (bytes): Image file content
            base_metadata (dict): Basic metadata from IngestionService
        
        Returns:
            dict: Image-specific metadata
                {
                    "width_pixels": <int or null>,
                    "height_pixels": <int or null>,
                    "color_space": "RGB" | "RGBA" | null,
                    "dpi": <int or null>,
                    "mime_type": "image/png"
                }
        """
        result = {
            "width_pixels": None,
            "height_pixels": None,
            "color_space": None,
            "dpi": None,
            "mime_type": "image/png",
        }
        
        # Try to extract basic resolution from PNG header if present
        extension = base_metadata.get("extension", "").lower()
        
        if extension == ".png":
            result["mime_type"] = "image/png"
            # PNG: width and height at bytes 16-24
            if len(data) >= 24:
                try:
                    width = int.from_bytes(data[16:20], 'big')
                    height = int.from_bytes(data[20:24], 'big')
                    if width > 0 and height > 0:
                        result["width_pixels"] = width
                        result["height_pixels"] = height
                        result["color_space"] = "RGBA"
                except Exception:
                    pass
        
        elif extension in [".jpg", ".jpeg"]:
            result["mime_type"] = "image/jpeg"
            # JPEG resolution extraction is more complex, skip for now
        
        elif extension == ".webp":
            result["mime_type"] = "image/webp"
        
        elif extension == ".gif":
            result["mime_type"] = "image/gif"
        
        self.logger.info(f"Image metadata extracted: {result}")
        return result
    
    def _extract_text_metadata(self, data: str, base_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract text metadata.
        
        Args:
            data (str): Text file content
            base_metadata (dict): Basic metadata from IngestionService
        
        Returns:
            dict: Text-specific metadata
                {
                    "char_count": <int>,
                    "line_count": <int>,
                    "word_count": <int>,
                    "language": "ja" | "en" | null,
                    "encoding": "utf-8",
                    "mime_type": "text/plain"
                }
        """
        result = {
            "char_count": len(data) if isinstance(data, str) else 0,
            "line_count": len(data.split('\n')) if isinstance(data, str) else 0,
            "word_count": len(data.split()) if isinstance(data, str) else 0,
            "language": self._detect_language(data) if isinstance(data, str) else None,
            "encoding": base_metadata.get("encoding", "utf-8"),
            "mime_type": "text/plain",
        }
        
        # Adjust MIME type for Markdown
        extension = base_metadata.get("extension", "").lower()
        if extension == ".md":
            result["mime_type"] = "text/markdown"
        
        self.logger.info(f"Text metadata extracted: {result}")
        return result
    
    @staticmethod
    def _detect_language(text: str) -> Optional[str]:
        """
        Detect language of text (simple heuristic).
        
        Checks for presence of Japanese characters.
        
        Args:
            text (str): Text to analyze
        
        Returns:
            str: "ja" for Japanese, "en" for English, None if unclear
        """
        # Check for Japanese characters (Hiragana, Katakana, Kanji)
        japanese_chars = any('\u3040' <= char <= '\u309F' or  # Hiragana
                           '\u30A0' <= char <= '\u30FF' or  # Katakana
                           '\u4E00' <= char <= '\u9FFF'     # Kanji
                           for char in text)
        
        if japanese_chars:
            return "ja"
        
        # Check for English (basic heuristic)
        if any(char.isalpha() for char in text):
            return "en"
        
        return None


# ===== Helper Classes for Testing =====

class MockIngestedAsset:
    """Mock for testing purposes"""
    
    @staticmethod
    def create_text_asset(content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Create mock text asset"""
        return {
            "format": "text_only",
            "data": content,
            "metadata": {
                "file_path": "/tmp/test.txt",
                "file_name": "test.txt",
                "file_size_bytes": len(content.encode(encoding)),
                "extension": ".txt",
                "encoding": encoding,
                "char_count": len(content),
                "line_count": len(content.split('\n')),
                "file_exists": True,
                "is_readable": True,
            },
            "file_path": "/tmp/test.txt"
        }
    
    @staticmethod
    def create_video_asset(size: int = 1024 * 1024) -> Dict[str, Any]:
        """Create mock video asset"""
        return {
            "format": "video_static",
            "data": b'\x00\x00\x00\x20ftypisom' + (b'\x00' * (size - 12)),
            "metadata": {
                "file_path": "/tmp/test.mp4",
                "file_name": "test.mp4",
                "file_size_bytes": size,
                "extension": ".mp4",
                "file_exists": True,
                "is_readable": True,
            },
            "file_path": "/tmp/test.mp4"
        }
    
    @staticmethod
    def create_image_asset() -> Dict[str, Any]:
        """Create mock image asset"""
        # Simple PNG header with 640x480 resolution
        png_header = b'\x89PNG\r\n\x1a\n'
        width_height = b'\x00\x00\x02\x80\x00\x00\x01\xe0'  # 640x480 in big-endian
        png_data = png_header + b'\x00' * 8 + width_height + (b'\x00' * 100)
        
        return {
            "format": "image_static",
            "data": png_data,
            "metadata": {
                "file_path": "/tmp/test.png",
                "file_name": "test.png",
                "file_size_bytes": len(png_data),
                "extension": ".png",
                "file_exists": True,
                "is_readable": True,
            },
            "file_path": "/tmp/test.png"
        }
