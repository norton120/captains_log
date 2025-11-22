"""Audio chunking utility for splitting large audio files into processable chunks."""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List

import ffmpeg

logger = logging.getLogger(__name__)


class AudioChunkingError(Exception):
    """Exception raised when audio chunking fails."""
    pass


class AudioChunker:
    """Service for chunking large audio files into smaller segments."""

    # OpenAI Whisper API has a 25MB file size limit
    DEFAULT_MAX_SIZE_MB = 20  # Target 20MB chunks to stay safely under the limit

    def __init__(self, max_chunk_size_mb: float = DEFAULT_MAX_SIZE_MB):
        """
        Initialize the audio chunker.

        Args:
            max_chunk_size_mb: Maximum size in MB for each chunk (default 20MB)
        """
        self.max_chunk_size_bytes = int(max_chunk_size_mb * 1024 * 1024)

    async def chunk_audio_file(
        self,
        audio_file: Path,
        chunk_duration_seconds: int = 600  # 10 minutes default
    ) -> List[Path]:
        """
        Split an audio file into chunks based on duration.

        This method uses ffmpeg to split audio files into chunks of a specified duration.
        Each chunk is saved as a separate temporary file.

        Args:
            audio_file: Path to the audio file to chunk
            chunk_duration_seconds: Duration of each chunk in seconds (default 600 = 10 min)

        Returns:
            List of paths to chunk files

        Raises:
            AudioChunkingError: If chunking fails
        """
        try:
            logger.info(f"Chunking audio file: {audio_file}")

            # Validate input file exists
            if not audio_file.exists():
                raise AudioChunkingError(f"Audio file not found: {audio_file}")

            # Get audio duration
            duration = await self._get_audio_duration(audio_file)

            if duration <= 0:
                raise AudioChunkingError("Could not determine audio duration")

            # Calculate optimal chunk duration based on file size and duration
            file_size = audio_file.stat().st_size
            chunk_duration = await self._calculate_optimal_chunk_duration(
                file_size, duration, chunk_duration_seconds
            )

            logger.info(f"Splitting {duration:.1f}s audio into {chunk_duration}s chunks")

            # Split audio file into chunks
            chunk_files = await self._split_audio_into_chunks(
                audio_file, chunk_duration, duration
            )

            logger.info(f"Created {len(chunk_files)} audio chunks")
            return chunk_files

        except Exception as e:
            logger.error(f"Audio chunking failed: {e}")
            raise AudioChunkingError(f"Failed to chunk audio: {str(e)}")

    async def _get_audio_duration(self, audio_file: Path) -> float:
        """
        Get the duration of an audio file in seconds.

        Args:
            audio_file: Path to audio file

        Returns:
            Duration in seconds

        Raises:
            AudioChunkingError: If probe fails
        """
        try:
            probe = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', str(audio_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await probe.communicate()

            if probe.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "Unknown ffprobe error"
                raise AudioChunkingError(f"FFprobe failed: {error_msg}")

            import json
            probe_data = json.loads(stdout.decode('utf-8'))

            format_info = probe_data.get('format', {})
            duration = float(format_info.get('duration', 0))

            return duration

        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            raise AudioChunkingError(f"Could not determine audio duration: {str(e)}")

    async def _calculate_optimal_chunk_duration(
        self,
        file_size: int,
        duration: float,
        max_chunk_duration: int
    ) -> int:
        """
        Calculate optimal chunk duration to stay under size limit.

        Args:
            file_size: Size of the file in bytes
            duration: Duration of the audio in seconds
            max_chunk_duration: Maximum desired chunk duration in seconds

        Returns:
            Optimal chunk duration in seconds
        """
        # Calculate bytes per second
        bytes_per_second = file_size / duration

        # Calculate duration that would result in max_chunk_size_bytes
        optimal_duration = self.max_chunk_size_bytes / bytes_per_second

        # Use the smaller of optimal duration or max chunk duration
        # Round down to ensure we stay under the limit
        chunk_duration = min(int(optimal_duration * 0.9), max_chunk_duration)

        # Ensure minimum chunk duration of 60 seconds
        chunk_duration = max(chunk_duration, 60)

        logger.info(
            f"File size: {file_size / (1024*1024):.1f}MB, "
            f"Duration: {duration:.1f}s, "
            f"Calculated chunk duration: {chunk_duration}s"
        )

        return chunk_duration

    async def _split_audio_into_chunks(
        self,
        audio_file: Path,
        chunk_duration: int,
        total_duration: float
    ) -> List[Path]:
        """
        Split audio file into chunks using ffmpeg.

        Args:
            audio_file: Path to input audio file
            chunk_duration: Duration of each chunk in seconds
            total_duration: Total duration of the audio file

        Returns:
            List of paths to chunk files

        Raises:
            AudioChunkingError: If splitting fails
        """
        chunk_files = []

        try:
            # Calculate number of chunks needed
            num_chunks = int((total_duration / chunk_duration)) + 1

            for i in range(num_chunks):
                start_time = i * chunk_duration

                # Don't create a chunk if start time is past total duration
                if start_time >= total_duration:
                    break

                # Create temporary file for this chunk
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=audio_file.suffix,
                    prefix=f"chunk_{i:03d}_"
                ) as temp_file:
                    chunk_path = Path(temp_file.name)

                # Extract chunk using ffmpeg
                await self._extract_audio_chunk(
                    audio_file, chunk_path, start_time, chunk_duration
                )

                # Validate chunk was created
                if chunk_path.exists() and chunk_path.stat().st_size > 0:
                    chunk_files.append(chunk_path)
                    logger.debug(
                        f"Created chunk {i}: {chunk_path.name} "
                        f"({chunk_path.stat().st_size / (1024*1024):.1f}MB)"
                    )
                else:
                    logger.warning(f"Chunk {i} was not created or is empty")

            return chunk_files

        except Exception as e:
            # Clean up any created chunks on failure
            for chunk_file in chunk_files:
                try:
                    chunk_file.unlink()
                except:
                    pass
            raise AudioChunkingError(f"Failed to split audio into chunks: {str(e)}")

    async def _extract_audio_chunk(
        self,
        input_file: Path,
        output_file: Path,
        start_time: int,
        duration: int
    ) -> None:
        """
        Extract a chunk of audio using ffmpeg.

        Args:
            input_file: Input audio file path
            output_file: Output chunk file path
            start_time: Start time in seconds
            duration: Duration of chunk in seconds

        Raises:
            AudioChunkingError: If ffmpeg command fails
        """
        try:
            # Build ffmpeg command
            input_stream = ffmpeg.input(str(input_file), ss=start_time, t=duration)
            output_stream = ffmpeg.output(
                input_stream,
                str(output_file),
                acodec='copy',  # Copy audio codec to avoid re-encoding
                loglevel='error'
            )

            # Run ffmpeg command asynchronously
            process = await asyncio.create_subprocess_exec(
                *ffmpeg.compile(output_stream, overwrite_output=True),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "Unknown ffmpeg error"
                raise AudioChunkingError(
                    f"FFmpeg chunk extraction failed with code {process.returncode}: {error_msg}"
                )

            logger.debug(f"FFmpeg chunk extraction completed successfully")

        except FileNotFoundError:
            raise AudioChunkingError(
                "FFmpeg not found. Please install FFmpeg to chunk audio files."
            )
        except Exception as e:
            raise AudioChunkingError(f"FFmpeg chunk extraction failed: {str(e)}")

    @staticmethod
    def cleanup_chunks(chunk_files: List[Path]) -> None:
        """
        Clean up temporary chunk files.

        Args:
            chunk_files: List of chunk file paths to delete
        """
        for chunk_file in chunk_files:
            try:
                if chunk_file.exists():
                    chunk_file.unlink()
                    logger.debug(f"Cleaned up chunk: {chunk_file.name}")
            except Exception as e:
                logger.warning(f"Failed to clean up chunk {chunk_file}: {e}")
