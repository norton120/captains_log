"""Tests for video processing functionality."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.video_processor import VideoProcessor, VideoProcessingError
from app.workflows.audio_processor import VideoPreprocessStep, AudioProcessingWorkflow
from app.models.log_entry import LogEntry, MediaType, ProcessingStatus


class TestVideoProcessor:
    """Test cases for VideoProcessor service."""

    @pytest.fixture
    def processor(self):
        """Create a VideoProcessor instance."""
        return VideoProcessor()

    def test_is_video_file(self, processor):
        """Test video file detection."""
        # Video files
        assert processor.is_video_file(Path("test.mp4"))
        assert processor.is_video_file(Path("test.webm"))
        assert processor.is_video_file(Path("test.mov"))
        assert processor.is_video_file(Path("test.avi"))

        # Audio files
        assert not processor.is_video_file(Path("test.wav"))
        assert not processor.is_video_file(Path("test.mp3"))
        assert not processor.is_video_file(Path("test.flac"))

        # Case insensitive
        assert processor.is_video_file(Path("test.MP4"))
        assert processor.is_video_file(Path("test.WEBM"))

    @pytest.mark.asyncio
    async def test_extract_audio_from_video_file_not_found(self, processor):
        """Test audio extraction with missing file."""
        non_existent_file = Path("/path/to/non_existent_video.mp4")

        with pytest.raises(VideoProcessingError, match="Video file not found"):
            await processor.extract_audio_from_video(non_existent_file)

    @pytest.mark.asyncio
    @patch("app.services.video_processor.asyncio.create_subprocess_exec")
    async def test_extract_audio_from_video_success(self, mock_subprocess, processor):
        """Test successful audio extraction from video."""
        # Create a temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(b"fake video data")
            video_path = Path(temp_video.name)

        try:
            # Mock ffmpeg process
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"", b"")
            mock_subprocess.return_value = mock_process

            # Mock successful extraction - create output file
            with patch("pathlib.Path.exists") as mock_exists:
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 1000  # Non-zero size
                    mock_exists.return_value = True

                    # Extract audio
                    audio_file = await processor.extract_audio_from_video(video_path)

                    # Verify result
                    assert audio_file.suffix == ".wav"
                    assert "extracted_audio_" in audio_file.name

                    # Verify ffmpeg was called
                    mock_subprocess.assert_called_once()
                    args = mock_subprocess.call_args[0]
                    assert any("ffmpeg" in str(arg) for arg in args[0])

        finally:
            # Clean up
            video_path.unlink()

    @pytest.mark.asyncio
    @patch("app.services.video_processor.asyncio.create_subprocess_exec")
    async def test_extract_audio_ffmpeg_failure(self, mock_subprocess, processor):
        """Test ffmpeg failure handling."""
        # Create a temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(b"fake video data")
            video_path = Path(temp_video.name)

        try:
            # Mock ffmpeg failure
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"FFmpeg error message")
            mock_subprocess.return_value = mock_process

            with pytest.raises(VideoProcessingError, match="FFmpeg failed with code 1"):
                await processor.extract_audio_from_video(video_path)

        finally:
            # Clean up
            video_path.unlink()

    @pytest.mark.asyncio
    @patch("app.services.video_processor.asyncio.create_subprocess_exec")
    async def test_get_video_info_success(self, mock_subprocess, processor):
        """Test successful video info extraction."""
        # Create a temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(b"fake video data")
            video_path = Path(temp_video.name)

        try:
            # Mock ffprobe output
            probe_output = {
                "format": {"duration": "120.5", "size": "1024000", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
                "streams": [
                    {"codec_type": "video", "width": 1280, "height": 720},
                    {"codec_type": "audio", "channels": 2},
                ],
            }

            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (str(probe_output).replace("'", '"').encode(), b"")
            mock_subprocess.return_value = mock_process

            # Get video info
            with patch("json.loads") as mock_json:
                mock_json.return_value = probe_output

                info = await processor.get_video_info(video_path)

                # Verify result
                assert info["duration"] == 120.5
                assert info["size"] == 1024000
                assert info["format_name"] == "mov,mp4,m4a,3gp,3g2,mj2"
                assert info["video_streams"] == 1
                assert info["audio_streams"] == 1
                assert info["has_audio"] is True

        finally:
            # Clean up
            video_path.unlink()


class TestVideoPreprocessStep:
    """Test cases for VideoPreprocessStep workflow step."""

    @pytest.fixture
    def mock_workflow(self):
        """Create a mock workflow instance."""
        workflow = MagicMock(spec=AudioProcessingWorkflow)
        workflow.settings = MagicMock()
        workflow.db_session = MagicMock()
        workflow.media_storage = MagicMock()
        workflow.openai_service = MagicMock()
        return workflow

    @pytest.fixture
    def preprocess_step(self, mock_workflow):
        """Create a VideoPreprocessStep instance."""
        return VideoPreprocessStep(mock_workflow)

    @pytest.mark.asyncio
    async def test_preprocess_audio_file(self, preprocess_step):
        """Test preprocessing of audio file (no conversion needed)."""
        # Create a temporary audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            temp_audio.write(b"fake audio data")
            audio_path = Path(temp_audio.name)

        try:
            # Process audio file
            result = await preprocess_step.execute(audio_path)

            # Verify result
            assert result["success"] is True
            assert result["audio_file"] == audio_path
            assert result["original_file"] == audio_path
            assert result["is_video"] is False
            assert result["extracted_audio"] is False

        finally:
            # Clean up
            audio_path.unlink()

    @pytest.mark.asyncio
    async def test_preprocess_video_file(self, preprocess_step):
        """Test preprocessing of video file (audio extraction needed)."""
        # Create a temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(b"fake video data")
            video_path = Path(temp_video.name)

        try:
            # Mock video processor methods
            mock_video_info = {"duration": 60.0, "size": 1000000, "has_audio": True}

            with patch.object(preprocess_step.video_processor, "get_video_info") as mock_info:
                with patch.object(preprocess_step.video_processor, "extract_audio_from_video") as mock_extract:
                    # Create temporary extracted audio file
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                        extracted_audio_path = Path(temp_audio.name)

                    mock_info.return_value = mock_video_info
                    mock_extract.return_value = extracted_audio_path

                    # Process video file
                    result = await preprocess_step.execute(video_path)

                    # Verify result
                    assert result["success"] is True
                    assert result["audio_file"] == extracted_audio_path
                    assert result["original_file"] == video_path
                    assert result["is_video"] is True
                    assert result["extracted_audio"] is True
                    assert result["video_info"] == mock_video_info

                    # Verify video processor was called
                    mock_info.assert_called_once_with(video_path)
                    mock_extract.assert_called_once_with(video_path, output_format="wav", sample_rate=44100)

                    # Clean up extracted audio file
                    extracted_audio_path.unlink()

        finally:
            # Clean up
            video_path.unlink()

    @pytest.mark.asyncio
    async def test_preprocess_video_no_audio(self, preprocess_step):
        """Test preprocessing of video file without audio track."""
        # Create a temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(b"fake video data")
            video_path = Path(temp_video.name)

        try:
            # Mock video processor methods
            mock_video_info = {"duration": 60.0, "size": 1000000, "has_audio": False}

            with patch.object(preprocess_step.video_processor, "get_video_info") as mock_info:
                mock_info.return_value = mock_video_info

                # Process video file
                with pytest.raises(Exception, match="Video file contains no audio track"):
                    await preprocess_step.execute(video_path)

        finally:
            # Clean up
            video_path.unlink()

    @pytest.mark.asyncio
    async def test_preprocess_file_not_found(self, preprocess_step):
        """Test preprocessing with non-existent file."""
        non_existent_file = Path("/path/to/non_existent.mp4")

        with pytest.raises(Exception, match="File not found"):
            await preprocess_step.execute(non_existent_file)


@pytest.mark.asyncio
async def test_media_type_enum():
    """Test MediaType enum values."""
    assert MediaType.AUDIO.value == "audio"
    assert MediaType.VIDEO.value == "video"

    # Test creating log entry with video type
    log_entry = LogEntry(media_type=MediaType.VIDEO, original_filename="test_video.mp4", is_video_source=True)

    assert log_entry.media_type == MediaType.VIDEO
    assert log_entry.original_filename == "test_video.mp4"
    assert log_entry.is_video_source is True
