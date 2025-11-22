"""Tests for audio chunking service."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audio_chunker import AudioChunker, AudioChunkingError


@pytest.fixture
def audio_chunker():
    """Create an AudioChunker instance for testing."""
    return AudioChunker(max_chunk_size_mb=20)


@pytest.fixture
def mock_audio_file(tmp_path):
    """Create a mock audio file for testing."""
    audio_file = tmp_path / "test_audio.wav"
    # Create a file with some data
    audio_file.write_bytes(b"fake audio data" * 1000)
    return audio_file


class TestAudioChunker:
    """Test suite for AudioChunker class."""

    @pytest.mark.asyncio
    async def test_chunk_audio_file_not_found(self, audio_chunker):
        """Test that chunking fails gracefully when file doesn't exist."""
        non_existent_file = Path("/nonexistent/audio.wav")

        with pytest.raises(AudioChunkingError, match="Audio file not found"):
            await audio_chunker.chunk_audio_file(non_existent_file)

    @pytest.mark.asyncio
    async def test_get_audio_duration(self, audio_chunker, mock_audio_file):
        """Test getting audio duration using ffprobe."""
        # Mock the subprocess call
        mock_probe_data = {"format": {"duration": "123.45"}}

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Create mock process
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (str(mock_probe_data).replace("'", '"').encode("utf-8"), b"")
            mock_subprocess.return_value = mock_process

            duration = await audio_chunker._get_audio_duration(mock_audio_file)

            assert duration == 123.45
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_duration_ffprobe_error(self, audio_chunker, mock_audio_file):
        """Test that ffprobe errors are handled correctly."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Create mock process with error
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"ffprobe error")
            mock_subprocess.return_value = mock_process

            with pytest.raises(AudioChunkingError, match="FFprobe failed"):
                await audio_chunker._get_audio_duration(mock_audio_file)

    @pytest.mark.asyncio
    async def test_calculate_optimal_chunk_duration(self, audio_chunker):
        """Test calculation of optimal chunk duration."""
        # Test case: 50MB file, 1000 seconds duration
        # bytes_per_second = 50MB / 1000s = 50KB/s
        # For 20MB chunks: 20MB / 50KB/s = 400s
        file_size = 50 * 1024 * 1024  # 50MB
        duration = 1000.0  # 1000 seconds
        max_chunk_duration = 600  # 10 minutes

        chunk_duration = await audio_chunker._calculate_optimal_chunk_duration(file_size, duration, max_chunk_duration)

        # Should return optimal duration (with 0.9 safety factor)
        # 400 * 0.9 = 360 seconds
        assert chunk_duration == 360

    @pytest.mark.asyncio
    async def test_calculate_optimal_chunk_duration_respects_max(self, audio_chunker):
        """Test that optimal chunk duration respects maximum."""
        # Test case: Small file that could have long chunks
        file_size = 5 * 1024 * 1024  # 5MB
        duration = 1000.0  # 1000 seconds
        max_chunk_duration = 300  # 5 minutes

        chunk_duration = await audio_chunker._calculate_optimal_chunk_duration(file_size, duration, max_chunk_duration)

        # Should cap at max_chunk_duration
        assert chunk_duration == max_chunk_duration

    @pytest.mark.asyncio
    async def test_calculate_optimal_chunk_duration_minimum(self, audio_chunker):
        """Test that optimal chunk duration has a minimum value."""
        # Test case: Very large file with short duration
        file_size = 100 * 1024 * 1024  # 100MB
        duration = 10.0  # 10 seconds
        max_chunk_duration = 600

        chunk_duration = await audio_chunker._calculate_optimal_chunk_duration(file_size, duration, max_chunk_duration)

        # Should return minimum of 60 seconds
        assert chunk_duration == 60

    @pytest.mark.asyncio
    async def test_extract_audio_chunk(self, audio_chunker, tmp_path):
        """Test extracting a single audio chunk."""
        input_file = tmp_path / "input.wav"
        output_file = tmp_path / "output.wav"
        input_file.write_bytes(b"fake audio data")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Create mock process
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"", b"")
            mock_subprocess.return_value = mock_process

            # Create output file to simulate ffmpeg success
            output_file.write_bytes(b"chunk data")

            await audio_chunker._extract_audio_chunk(input_file, output_file, start_time=0, duration=60)

            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_audio_chunk_ffmpeg_error(self, audio_chunker, tmp_path):
        """Test that ffmpeg errors are handled correctly."""
        input_file = tmp_path / "input.wav"
        output_file = tmp_path / "output.wav"
        input_file.write_bytes(b"fake audio data")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Create mock process with error
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"ffmpeg error")
            mock_subprocess.return_value = mock_process

            with pytest.raises(AudioChunkingError, match="FFmpeg chunk extraction failed"):
                await audio_chunker._extract_audio_chunk(input_file, output_file, start_time=0, duration=60)

    @pytest.mark.asyncio
    async def test_split_audio_into_chunks(self, audio_chunker, tmp_path):
        """Test splitting audio into multiple chunks."""
        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake audio data")

        # Mock ffmpeg subprocess to create actual chunk files
        async def mock_create_chunk(*args, **kwargs):
            # Extract output file from ffmpeg compile args
            # Create a small chunk file
            import tempfile

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", prefix="chunk_")
            temp_file.write(b"chunk data")
            temp_file.close()

            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"", b"")
            return mock_process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_chunk):
            with patch.object(audio_chunker, "_extract_audio_chunk") as mock_extract:
                # Mock extract to create files
                async def create_chunk_file(input_f, output_f, start_t, dur):
                    output_f.write_bytes(b"chunk data")

                mock_extract.side_effect = create_chunk_file

                chunks = await audio_chunker._split_audio_into_chunks(
                    input_file, chunk_duration=100, total_duration=250
                )

                # Should create 3 chunks (0-100, 100-200, 200-250)
                assert len(chunks) == 3

                # Clean up
                AudioChunker.cleanup_chunks(chunks)

    @pytest.mark.asyncio
    async def test_chunk_audio_file_integration(self, audio_chunker, mock_audio_file):
        """Test full chunking workflow with mocked subprocess calls."""
        # Mock duration
        mock_duration = 300.0  # 5 minutes

        with patch.object(audio_chunker, "_get_audio_duration", return_value=mock_duration):
            with patch.object(audio_chunker, "_split_audio_into_chunks") as mock_split:
                # Mock return chunks
                mock_chunks = [Path("/tmp/chunk_000.wav"), Path("/tmp/chunk_001.wav")]
                mock_split.return_value = mock_chunks

                chunks = await audio_chunker.chunk_audio_file(mock_audio_file)

                assert len(chunks) == 2
                mock_split.assert_called_once()

    def test_cleanup_chunks(self, tmp_path):
        """Test cleanup of chunk files."""
        # Create some temporary chunk files
        chunk_files = []
        for i in range(3):
            chunk_file = tmp_path / f"chunk_{i}.wav"
            chunk_file.write_bytes(b"chunk data")
            chunk_files.append(chunk_file)

        # Verify files exist
        for chunk_file in chunk_files:
            assert chunk_file.exists()

        # Clean up
        AudioChunker.cleanup_chunks(chunk_files)

        # Verify files are deleted
        for chunk_file in chunk_files:
            assert not chunk_file.exists()

    def test_cleanup_chunks_handles_missing_files(self):
        """Test that cleanup handles missing files gracefully."""
        # Create list with non-existent files
        chunk_files = [Path("/nonexistent/chunk_0.wav"), Path("/nonexistent/chunk_1.wav")]

        # Should not raise an error
        AudioChunker.cleanup_chunks(chunk_files)
