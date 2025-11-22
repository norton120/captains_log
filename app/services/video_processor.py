"""Video processing service for extracting audio from video files."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

import ffmpeg

logger = logging.getLogger(__name__)


class VideoProcessingError(Exception):
    """Exception raised when video processing fails."""

    pass


class VideoProcessor:
    """Service for processing video files and extracting audio."""

    def __init__(self):
        """Initialize the video processor."""
        pass

    async def extract_audio_from_video(
        self, video_file: Path, output_format: str = "wav", sample_rate: int = 44100
    ) -> Path:
        """
        Extract audio from video file asynchronously.

        Args:
            video_file: Path to the video file
            output_format: Audio format to extract (wav, mp3, etc.)
            sample_rate: Sample rate for extracted audio

        Returns:
            Path to the extracted audio file

        Raises:
            VideoProcessingError: If extraction fails
        """
        try:
            logger.info(f"Extracting audio from video: {video_file}")

            # Validate input file exists
            if not video_file.exists():
                raise VideoProcessingError(f"Video file not found: {video_file}")

            # Create temporary output file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f".{output_format}", prefix="extracted_audio_"
            ) as temp_file:
                output_path = Path(temp_file.name)

            # Extract audio using ffmpeg in a subprocess
            await self._run_ffmpeg_extract(video_file, output_path, sample_rate)

            # Validate output file was created
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise VideoProcessingError("Audio extraction failed - no output file generated")

            logger.info(f"Audio extracted successfully: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            raise VideoProcessingError(f"Failed to extract audio: {str(e)}")

    async def _run_ffmpeg_extract(self, video_file: Path, audio_file: Path, sample_rate: int) -> None:
        """
        Run ffmpeg command to extract audio in a subprocess.

        Args:
            video_file: Input video file path
            audio_file: Output audio file path
            sample_rate: Audio sample rate

        Raises:
            VideoProcessingError: If ffmpeg command fails
        """
        try:
            # Build ffmpeg command
            input_stream = ffmpeg.input(str(video_file))
            output_stream = ffmpeg.output(
                input_stream,
                str(audio_file),
                acodec="pcm_s16le",  # PCM 16-bit for WAV
                ar=sample_rate,  # Sample rate
                ac=1,  # Mono audio
                loglevel="error",  # Only show errors
            )

            # Run ffmpeg command asynchronously
            process = await asyncio.create_subprocess_exec(
                *ffmpeg.compile(output_stream, overwrite_output=True),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8") if stderr else "Unknown ffmpeg error"
                raise VideoProcessingError(f"FFmpeg failed with code {process.returncode}: {error_msg}")

            logger.debug(f"FFmpeg extraction completed successfully")

        except FileNotFoundError:
            raise VideoProcessingError("FFmpeg not found. Please install FFmpeg to process video files.")
        except Exception as e:
            raise VideoProcessingError(f"FFmpeg execution failed: {str(e)}")

    def is_video_file(self, file_path: Path) -> bool:
        """
        Check if a file is a video file based on extension.

        Args:
            file_path: Path to check

        Returns:
            True if file appears to be a video file
        """
        video_extensions = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
        return file_path.suffix.lower() in video_extensions

    async def get_video_info(self, video_file: Path) -> dict:
        """
        Get information about a video file.

        Args:
            video_file: Path to video file

        Returns:
            Dictionary with video information

        Raises:
            VideoProcessingError: If probe fails
        """
        try:
            probe = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await probe.communicate()

            if probe.returncode != 0:
                error_msg = stderr.decode("utf-8") if stderr else "Unknown ffprobe error"
                raise VideoProcessingError(f"FFprobe failed: {error_msg}")

            import json

            probe_data = json.loads(stdout.decode("utf-8"))

            # Extract useful information
            format_info = probe_data.get("format", {})
            video_streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"]
            audio_streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]

            return {
                "duration": float(format_info.get("duration", 0)),
                "size": int(format_info.get("size", 0)),
                "format_name": format_info.get("format_name", ""),
                "video_streams": len(video_streams),
                "audio_streams": len(audio_streams),
                "has_audio": len(audio_streams) > 0,
            }

        except Exception as e:
            logger.warning(f"Failed to get video info: {e}")
            return {
                "duration": 0,
                "size": 0,
                "format_name": "unknown",
                "video_streams": 0,
                "audio_streams": 0,
                "has_audio": False,
            }
