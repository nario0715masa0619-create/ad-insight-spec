"""
IngestionService - File Ingestion and Normalization

Responsibilities:
- Load files from disk (video/image/text)
- Validate file existence and format
- Normalize file data into IngestedAsset structure
- Handle errors gracefully

Returns:
- IngestedAsset: {"format": "video_static", "data": <bytes>, "metadata": {...}}
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from app.services.base_service import BaseService, ValidationError, ProcessingError


logger = logging.getLogger(__name__)


# Supported file formats
SUPPORTED_FORMATS = {
    'video': {
        'extensions': ['.mp4', '.mov', '.avi', '.mkv'],
        'format_key': 'video_static',
        'mime_types': ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska']
    },
    'image': {
        'extensions': ['.png', '.jpg', '.jpeg', '.webp', '.gif'],
        'format_key': 'image_static',
        'mime_types': ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
    },
    'text': {
        'extensions': ['.txt', '.md'],
        'format_key': 'text_only',
        'mime_types': ['text/plain', 'text/markdown']
    }
}


class IngestedAsset:
    """
    Data class representing ingested asset.
    
    Attributes:
        format (str): video_static / image_static / text_only
        data (bytes or str): File content (bytes for binary, str for text)
        metadata (dict): Basic file info (size, path, etc.)
        file_path (str): Original file path
    """
    
    def __init__(
        self,
        format: str,
        data: Any,
        metadata: Dict[str, Any],
        file_path: str
    ):
        self.format = format
        self.data = data
        self.metadata = metadata
        self.file_path = file_path
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for passing between services"""
        return {
            "format": self.format,
            "data": self.data,
            "metadata": self.metadata,
            "file_path": self.file_path
        }


class IngestionService(BaseService):
    """
    Service for ingesting and normalizing creative files.
    
    Supports:
    - Video: MP4, MOV, AVI, MKV
    - Image: PNG, JPG, JPEG, WebP, GIF
    - Text: TXT, MD
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def execute(self, file_path: str) -> Dict[str, Any]:
        """
        Ingest a file and return normalized IngestedAsset.
        
        Args:
            file_path (str): Path to file
        
        Returns:
            dict: {"format": "...", "data": ..., "metadata": {...}, "file_path": "..."}
        
        Raises:
            ValidationError: File not found, unsupported format
            ProcessingError: File read error, corruption
        """
        self.logger.info(f"Ingesting file: {file_path}")
        
        # Validate file exists
        self.validate_file_exists(file_path)
        
        # Determine format
        file_format = self.detect_format(file_path)
        self.logger.info(f"Detected format: {file_format}")
        
        # Read file based on format
        if self._is_video(file_format):
            asset = self._ingest_video(file_path)
        elif self._is_image(file_format):
            asset = self._ingest_image(file_path)
        elif self._is_text(file_format):
            asset = self._ingest_text(file_path)
        else:
            raise ValidationError(f"Unsupported format: {file_format}")
        
        self.logger.info(f"Ingestion successful: {asset.format}, {len(asset.data)} bytes")
        return asset.to_dict()
    
    def validate_input(self, file_path: str) -> bool:
        """Validate that file path is a string"""
        if not isinstance(file_path, str):
            raise ValidationError(f"file_path must be string, got {type(file_path)}")
        return True
    
    def validate_file_exists(self, file_path: str) -> bool:
        """
        Validate that file exists and is readable.
        
        Args:
            file_path (str): Path to file
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If file not found or not readable
        """
        path = Path(file_path)
        
        if not path.exists():
            raise ValidationError(f"File not found: {file_path}")
        
        if not path.is_file():
            raise ValidationError(f"Path is not a file: {file_path}")
        
        if not os.access(file_path, os.R_OK):
            raise ValidationError(f"File is not readable: {file_path}")
        
        return True
    
    def detect_format(self, file_path: str) -> str:
        """
        Detect file format based on extension.
        
        Args:
            file_path (str): Path to file
        
        Returns:
            str: Format key (video_static / image_static / text_only)
        
        Raises:
            ValidationError: If format is unsupported
        """
        path = Path(file_path)
        extension = path.suffix.lower()
        
        # Check video
        if extension in SUPPORTED_FORMATS['video']['extensions']:
            return SUPPORTED_FORMATS['video']['format_key']
        
        # Check image
        if extension in SUPPORTED_FORMATS['image']['extensions']:
            return SUPPORTED_FORMATS['image']['format_key']
        
        # Check text
        if extension in SUPPORTED_FORMATS['text']['extensions']:
            return SUPPORTED_FORMATS['text']['format_key']
        
        raise ValidationError(
            f"Unsupported file format: {extension}. "
            f"Supported: {', '.join(SUPPORTED_FORMATS['video']['extensions'] + SUPPORTED_FORMATS['image']['extensions'] + SUPPORTED_FORMATS['text']['extensions'])}"
        )
    
    def _ingest_video(self, file_path: str) -> IngestedAsset:
        """
        Ingest video file.
        
        Args:
            file_path (str): Path to video file
        
        Returns:
            IngestedAsset: Video asset
        
        Raises:
            ProcessingError: If file is corrupted or cannot be read
        """
        try:
            path = Path(file_path)
            
            # Read file as bytes
            with open(file_path, 'rb') as f:
                data = f.read()
            
            if len(data) == 0:
                raise ProcessingError(f"Video file is empty: {file_path}")
            
            # Validate basic MP4/MOV structure (first 4 bytes)
            # This is a simple heuristic, not foolproof
            if not self._validate_video_header(data):
                self.logger.warning(f"Video header validation failed (may still be valid): {file_path}")
            
            # Extract basic metadata
            metadata = {
                "file_path": str(path.absolute()),
                "file_name": path.name,
                "file_size_bytes": len(data),
                "extension": path.suffix.lower(),
                "file_exists": True,
                "is_readable": True,
            }
            
            return IngestedAsset(
                format='video_static',
                data=data,
                metadata=metadata,
                file_path=file_path
            )
        
        except Exception as e:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(f"Failed to ingest video: {str(e)}")
    
    def _ingest_image(self, file_path: str) -> IngestedAsset:
        """
        Ingest image file.
        
        Args:
            file_path (str): Path to image file
        
        Returns:
            IngestedAsset: Image asset
        
        Raises:
            ProcessingError: If file is corrupted or cannot be read
        """
        try:
            path = Path(file_path)
            
            # Read file as bytes
            with open(file_path, 'rb') as f:
                data = f.read()
            
            if len(data) == 0:
                raise ProcessingError(f"Image file is empty: {file_path}")
            
            # Validate basic image header
            if not self._validate_image_header(data):
                self.logger.warning(f"Image header validation failed (may still be valid): {file_path}")
            
            # Extract basic metadata
            metadata = {
                "file_path": str(path.absolute()),
                "file_name": path.name,
                "file_size_bytes": len(data),
                "extension": path.suffix.lower(),
                "file_exists": True,
                "is_readable": True,
            }
            
            return IngestedAsset(
                format='image_static',
                data=data,
                metadata=metadata,
                file_path=file_path
            )
        
        except Exception as e:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(f"Failed to ingest image: {str(e)}")
    
    def _ingest_text(self, file_path: str) -> IngestedAsset:
        """
        Ingest text file.
        
        Args:
            file_path (str): Path to text file
        
        Returns:
            IngestedAsset: Text asset
        
        Raises:
            ProcessingError: If file cannot be read
        """
        try:
            path = Path(file_path)
            
            # Try multiple encodings
            encodings = ['utf-8', 'utf-8-sig', 'shift_jis', 'latin-1']
            data = None
            detected_encoding = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        data = f.read()
                    detected_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if data is None:
                raise ProcessingError(f"Could not decode text file with any supported encoding: {file_path}")
            
            if len(data) == 0:
                raise ProcessingError(f"Text file is empty: {file_path}")
            
            # Extract basic metadata
            metadata = {
                "file_path": str(path.absolute()),
                "file_name": path.name,
                "file_size_bytes": os.path.getsize(file_path),
                "extension": path.suffix.lower(),
                "encoding": detected_encoding,
                "char_count": len(data),
                "line_count": len(data.split('\n')),
                "file_exists": True,
                "is_readable": True,
            }
            
            return IngestedAsset(
                format='text_only',
                data=data,
                metadata=metadata,
                file_path=file_path
            )
        
        except Exception as e:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(f"Failed to ingest text: {str(e)}")
    
    # Helper methods
    
    def _is_video(self, format_key: str) -> bool:
        """Check if format is video"""
        return format_key == SUPPORTED_FORMATS['video']['format_key']
    
    def _is_image(self, format_key: str) -> bool:
        """Check if format is image"""
        return format_key == SUPPORTED_FORMATS['image']['format_key']
    
    def _is_text(self, format_key: str) -> bool:
        """Check if format is text"""
        return format_key == SUPPORTED_FORMATS['text']['format_key']
    
    @staticmethod
    def _validate_video_header(data: bytes) -> bool:
        """
        Validate video file header.
        Simple check: MP4/MOV files should contain 'ftyp' or similar markers.
        """
        if len(data) < 12:
            return False
        
        # MP4: "ftyp" at offset 4
        if b'ftyp' in data[:20]:
            return True
        
        # MOV: "mdat" or "moov" markers
        if b'mdat' in data or b'moov' in data:
            return True
        
        return True  # Be permissive, FFmpeg will validate anyway
    
    @staticmethod
    def _validate_image_header(data: bytes) -> bool:
        """
        Validate image file header.
        Check for PNG, JPEG, WebP, GIF magic numbers.
        """
        if len(data) < 4:
            return False
        
        magic_numbers = [
            b'\x89PNG',  # PNG
            b'\xff\xd8\xff',  # JPEG
            b'GIF8',  # GIF
            b'RIFF',  # WebP (followed by WEBP at offset 8)
        ]
        
        for magic in magic_numbers:
            if data.startswith(magic):
                return True
        
        return True  # Be permissive
