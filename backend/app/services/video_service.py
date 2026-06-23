"""
VideoService - Video Frame Extraction and Metadata

Responsibilities:
- Load and validate video files
- Extract metadata (duration, resolution, fps)
- Extract sampled frames at regular intervals using FFmpeg
- Generate thumbnail from first frame
- Return extracted frames and metadata

Input: video_file_path (str)
Output: dict with frames, duration, metadata

Note: This implementation uses FFmpeg for frame extraction.
Requires: ffmpeg command-line tool installed and in PATH
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
import json
import re

from app.services.base_service import BaseService, ValidationError, ProcessingError


logger = logging.getLogger(__name__)


class VideoService(BaseService):
    """
    Service for extracting frames and metadata from video files.
    
    Supports: MP4, MOV, AVI, MKV
    
    Uses FFmpeg for:
    - Duration/resolution/fps extraction
    - Key frame sampling (uniform distribution)
    - Thumbnail generation
    """
    
    def __init__(self, num_frames: int = 5, output_format: str = "png"):
        """
        Initialize VideoService.
        
        Args:
            num_frames (int): Number of frames to extract (default: 5)
            output_format (str): Output frame format (png, jpg)
        """
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.num_frames = num_frames
        self.output_format = output_format
        self.temp_dir = None
    
    def execute(self, video_path: str) -> Dict[str, Any]:
        """
        Extract video frames and metadata.
        
        Args:
            video_path (str): Path to video file
        
        Returns:
            dict: {
                "duration_seconds": 30.5,
                "resolution": "1920x1080",
                "fps": 24,
                "frame_count_estimate": 732,
                "sampled_frames": ["/tmp/frame_0.png", "/tmp/frame_1.png", ...],
                "thumbnail_path": "/tmp/thumb_0.png",
                "extraction_metadata": {
                    "codec": "h264",
                    "bitrate": "5000k",
                    "sample_method": "uniform"
                },
                "success": True,
                "message": ""
            }
        
        Raises:
            ValidationError: Invalid input
            ProcessingError: FFmpeg error or extraction failed
        """
        self.validate_input(video_path)
        
        try:
            self.logger.info(f"Processing video: {video_path}")
            
            # Get video metadata
            metadata = self._get_video_metadata(video_path)
            self.logger.info(f"Video metadata: {metadata}")
            
            # Extract frames
            frame_paths = self._extract_frames(video_path, metadata)
            self.logger.info(f"Extracted {len(frame_paths)} frames")
            
            # Generate thumbnail (use first frame)
            thumbnail_path = frame_paths[0] if frame_paths else None
            
            # Estimate frame count
            duration = metadata.get("duration", 0)
            fps = metadata.get("fps", 30)
            frame_count_estimate = int(duration * fps) if duration > 0 else 0
            
            result = {
                "duration_seconds": duration,
                "resolution": metadata.get("resolution"),
                "fps": fps,
                "frame_count_estimate": frame_count_estimate,
                "sampled_frames": frame_paths,
                "thumbnail_path": thumbnail_path,
                "extraction_metadata": {
                    "codec": metadata.get("codec"),
                    "bitrate": metadata.get("bitrate"),
                    "sample_method": "uniform",
                    "num_frames_requested": self.num_frames,
                    "num_frames_extracted": len(frame_paths),
                },
                "success": True,
                "message": f"Extracted {len(frame_paths)} frames from {duration:.2f}s video"
            }
            
            self.logger.info(f"Video processing successful: {result['message']}")
            return result
        
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to process video: {str(e)}")
    
    def validate_input(self, video_path: str) -> bool:
        """
        Validate video file input.
        
        Args:
            video_path (str): Path to video file
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If invalid
        """
        if not isinstance(video_path, str):
            raise ValidationError(f"video_path must be string, got {type(video_path)}")
        
        path = Path(video_path)
        
        if not path.exists():
            raise ValidationError(f"Video file not found: {video_path}")
        
        if not path.is_file():
            raise ValidationError(f"Path is not a file: {video_path}")
        
        # Check extension
        supported_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv']
        if path.suffix.lower() not in supported_extensions:
            raise ValidationError(
                f"Unsupported video format: {path.suffix}. "
                f"Supported: {', '.join(supported_extensions)}"
            )
        
        return True
    
    def _get_video_metadata(self, video_path: str) -> Dict[str, Any]:
        """
        Extract video metadata using FFprobe.
        
        Args:
            video_path (str): Path to video file
        
        Returns:
            dict: {duration, resolution, fps, codec, bitrate}
        
        Raises:
            ProcessingError: If FFprobe fails
        """
        try:
            # Use ffprobe to extract metadata as JSON
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=duration,width,height,r_frame_rate,codec_name,bit_rate',
                '-of', 'json',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                self.logger.warning(f"FFprobe failed, using fallback metadata")
                return self._get_fallback_metadata(video_path)
            
            data = json.loads(result.stdout)
            stream = data['streams'][0] if data['streams'] else {}
            
            # Extract duration (try multiple sources)
            duration = float(stream.get('duration', 0))
            if duration == 0:
                duration = self._get_duration_via_ffmpeg(video_path)
            
            # Extract resolution
            width = stream.get('width', 0)
            height = stream.get('height', 0)
            resolution = f"{width}x{height}" if width and height else "unknown"
            
            # Extract FPS
            fps_str = stream.get('r_frame_rate', '30/1')
            fps = self._parse_fps(fps_str)
            
            # Extract codec
            codec = stream.get('codec_name', 'unknown')
            
            # Extract bitrate
            bitrate = stream.get('bit_rate', 'unknown')
            
            return {
                "duration": duration,
                "resolution": resolution,
                "fps": fps,
                "codec": codec,
                "bitrate": bitrate,
            }
        
        except subprocess.TimeoutExpired:
            raise ProcessingError("FFprobe timeout")
        except Exception as e:
            self.logger.warning(f"Metadata extraction failed: {str(e)}, using fallback")
            return self._get_fallback_metadata(video_path)
    
    def _get_fallback_metadata(self, video_path: str) -> Dict[str, Any]:
        """
        Get minimal metadata when ffprobe fails.
        
        Uses FFmpeg to get duration.
        """
        duration = self._get_duration_via_ffmpeg(video_path)
        
        return {
            "duration": duration,
            "resolution": "unknown",
            "fps": 30,
            "codec": "unknown",
            "bitrate": "unknown",
        }
    
    def _get_duration_via_ffmpeg(self, video_path: str) -> float:
        """
        Extract duration using FFmpeg.
        
        Args:
            video_path (str): Path to video file
        
        Returns:
            float: Duration in seconds
        """
        try:
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-f', 'null',
                '-'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Parse duration from stderr
            # Format: Duration: HH:MM:SS.ms
            match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
            if match:
                hours, minutes, seconds = match.groups()
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            
            return 0.0
        
        except Exception as e:
            self.logger.warning(f"Duration extraction failed: {str(e)}")
            return 0.0
    
    def _parse_fps(self, fps_str: str) -> float:
        """
        Parse FPS from ffprobe format (e.g., "24/1" or "30000/1001").
        
        Args:
            fps_str (str): FPS string from ffprobe
        
        Returns:
            float: FPS value
        """
        try:
            if '/' in fps_str:
                num, denom = fps_str.split('/')
                return float(num) / float(denom)
            else:
                return float(fps_str)
        except:
            return 30.0  # Default
    
    def _extract_frames(self, video_path: str, metadata: Dict[str, Any]) -> List[str]:
        """
        Extract sampled frames from video.
        
        Uses FFmpeg with fps filter to extract frames at regular intervals.
        
        Args:
            video_path (str): Path to video file
            metadata (dict): Video metadata (contains duration)
        
        Returns:
            list: Paths to extracted frame files
        
        Raises:
            ProcessingError: If frame extraction fails
        """
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp(prefix="ad_insight_video_")
        
        try:
            duration = metadata.get("duration", 0)
            
            # Calculate FPS for frame extraction
            # fps = num_frames / duration
            if duration > 0:
                target_fps = self.num_frames / duration
            else:
                target_fps = 1  # 1 frame per second fallback
            
            self.logger.info(f"Extracting frames at ~{target_fps:.2f} fps")
            
            # FFmpeg command to extract frames
            frame_pattern = str(Path(self.temp_dir) / f"frame_%04d.{self.output_format}")
            
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vf', f'fps={target_fps}',
                '-q:v', '2',  # Quality (1-31, lower is better)
                frame_pattern
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                raise ProcessingError(f"FFmpeg frame extraction failed: {result.stderr}")
            
            # Collect extracted frames
            frame_dir = Path(self.temp_dir)
            frames = sorted(frame_dir.glob(f"frame_*.{self.output_format}"))
            frame_paths = [str(f) for f in frames]
            
            # Limit to requested number
            if len(frame_paths) > self.num_frames:
                # Keep evenly spaced frames
                indices = [int(i * len(frame_paths) / self.num_frames) for i in range(self.num_frames)]
                frame_paths = [frame_paths[i] for i in indices if i < len(frame_paths)]
            
            self.logger.info(f"Extracted {len(frame_paths)} frames")
            return frame_paths
        
        except subprocess.TimeoutExpired:
            raise ProcessingError("FFmpeg frame extraction timeout")
        except Exception as e:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(f"Frame extraction failed: {str(e)}")
    
    def cleanup(self):
        """Clean up temporary files"""
        if self.temp_dir:
            import shutil
            try:
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup: {str(e)}")
