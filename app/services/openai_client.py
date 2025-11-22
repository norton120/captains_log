"""OpenAI service for audio transcription, embeddings, and summarization."""
import asyncio
from pathlib import Path
from typing import List, Optional
import logging

from openai import OpenAI, AsyncOpenAI
from openai.types import CreateEmbeddingResponse
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion

from app.config import Settings
from app.services.audio_chunker import AudioChunker, AudioChunkingError

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Exception raised when audio transcription fails."""
    pass


class EmbeddingError(Exception):
    """Exception raised when embedding generation fails."""
    pass


class SummaryError(Exception):
    """Exception raised when summary generation fails."""
    pass


class ClassificationError(Exception):
    """Exception raised when log classification fails."""
    pass


class OpenAIService:
    """Service for OpenAI API interactions."""

    def __init__(self, settings: Settings):
        """Initialize OpenAI service with configuration."""
        self.settings = settings
        self._client = None
        self._async_client = None
        self._audio_chunker = None

        # Validate API key is set
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required")

    @property
    def client(self) -> OpenAI:
        """Lazy-loaded synchronous OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    @client.setter
    def client(self, value: OpenAI) -> None:
        """Allow setting client for testing."""
        self._client = value

    @property
    def async_client(self) -> AsyncOpenAI:
        """Lazy-loaded asynchronous OpenAI client."""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._async_client

    @async_client.setter
    def async_client(self, value: AsyncOpenAI) -> None:
        """Allow setting async client for testing."""
        self._async_client = value

    @property
    def audio_chunker(self) -> AudioChunker:
        """Lazy-loaded audio chunker."""
        if self._audio_chunker is None:
            self._audio_chunker = AudioChunker(max_chunk_size_mb=20)
        return self._audio_chunker

    @audio_chunker.setter
    def audio_chunker(self, value: AudioChunker) -> None:
        """Allow setting audio chunker for testing."""
        self._audio_chunker = value

    def _validate_audio_file(self, audio_file: Path, check_size: bool = True) -> bool:
        """
        Validate audio file for transcription.

        Args:
            audio_file: Path to audio file
            check_size: Whether to check file size (returns True if too large instead of raising)

        Returns:
            True if file needs chunking (too large), False otherwise

        Raises:
            TranscriptionError: If file is invalid
        """
        if not audio_file.exists():
            raise TranscriptionError(f"Audio file not found: {audio_file}")

        # Check file format
        allowed_extensions = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
        if audio_file.suffix.lower() not in allowed_extensions:
            raise TranscriptionError(
                f"Unsupported audio format: {audio_file.suffix}. "
                f"Allowed formats: {', '.join(allowed_extensions)}"
            )

        # Check file size (use configured max size, default OpenAI limit is 25MB)
        if check_size:
            file_size = audio_file.stat().st_size
            max_size = min(self.settings.max_audio_file_size, 25 * 1024 * 1024)  # Use settings or 25MB limit
            if file_size > max_size:
                # Return True to indicate file needs chunking
                size_mb = file_size / (1024 * 1024)
                max_mb = max_size / (1024 * 1024)
                logger.info(f"File too large: {size_mb:.1f}MB > {max_mb:.1f}MB - will use chunking")
                return True

        return False

    async def transcribe_audio(
        self,
        audio_file: Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Transcribe audio file using OpenAI Whisper.

        For files larger than 25MB, automatically chunks the audio into smaller
        segments, transcribes each chunk, and reassembles the full transcript.

        Args:
            audio_file: Path to audio file to transcribe
            language: ISO-639-1 language code (optional)
            prompt: Optional prompt to guide transcription
            temperature: Sampling temperature (0-1)

        Returns:
            Transcribed text

        Raises:
            TranscriptionError: If transcription fails
        """
        try:
            # Validate audio file and check if chunking is needed
            needs_chunking = self._validate_audio_file(audio_file, check_size=True)

            if needs_chunking:
                # Use chunked transcription for large files
                logger.info("Using chunked transcription for large audio file")
                return await self._transcribe_audio_chunked(
                    audio_file, language, prompt, temperature
                )
            else:
                # Use direct transcription for normal-sized files
                return await self._transcribe_audio_direct(
                    audio_file, language, prompt, temperature
                )

        except TranscriptionError:
            raise
        except Exception as e:
            error_msg = str(e)

            # Handle specific OpenAI errors
            if "rate limit" in error_msg.lower():
                raise TranscriptionError(f"Rate limit exceeded: {error_msg}")
            elif "authentication" in error_msg.lower() or "invalid api key" in error_msg.lower():
                raise TranscriptionError(f"Authentication failed: {error_msg}")
            elif "invalid" in error_msg.lower() and "file" in error_msg.lower():
                raise TranscriptionError(f"Invalid audio file: {error_msg}")
            else:
                raise TranscriptionError(f"Transcription failed: {error_msg}")

    async def _transcribe_audio_direct(
        self,
        audio_file: Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Transcribe audio file directly using OpenAI Whisper (for normal-sized files).

        Args:
            audio_file: Path to audio file to transcribe
            language: ISO-639-1 language code (optional)
            prompt: Optional prompt to guide transcription
            temperature: Sampling temperature (0-1)

        Returns:
            Transcribed text

        Raises:
            TranscriptionError: If transcription fails
        """
        try:
            # Prepare transcription parameters
            transcription_params = {
                "model": self.settings.openai_model_whisper,
                "file": open(audio_file, "rb"),
                "temperature": temperature,
                "response_format": "text"
            }

            if language:
                transcription_params["language"] = language

            if prompt:
                transcription_params["prompt"] = prompt

            # Run transcription in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            transcription = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                transcription_params
            )

            # Validate result
            if not transcription or not transcription.strip():
                raise TranscriptionError("Empty transcription result")

            logger.info(f"Successfully transcribed audio: {len(transcription)} characters")
            return transcription.strip()

        finally:
            # Ensure file is closed
            try:
                if 'transcription_params' in locals() and 'file' in transcription_params:
                    transcription_params['file'].close()
            except:
                pass

    async def _transcribe_audio_chunked(
        self,
        audio_file: Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Transcribe large audio file by chunking it into smaller segments.

        Args:
            audio_file: Path to audio file to transcribe
            language: ISO-639-1 language code (optional)
            prompt: Optional prompt to guide transcription
            temperature: Sampling temperature (0-1)

        Returns:
            Transcribed text assembled from all chunks

        Raises:
            TranscriptionError: If transcription fails
        """
        chunk_files = []
        try:
            # Chunk the audio file
            logger.info(f"Chunking audio file: {audio_file}")
            chunk_files = await self.audio_chunker.chunk_audio_file(audio_file)

            if not chunk_files:
                raise TranscriptionError("Failed to create audio chunks")

            logger.info(f"Created {len(chunk_files)} chunks, transcribing in parallel...")

            # Transcribe all chunks in parallel using asyncio.gather
            # Note: We can't use previous chunk context when parallelizing, but the speed
            # improvement from concurrent I/O is worth the minor loss of context
            async def transcribe_chunk(index: int, chunk_file: Path) -> tuple[int, str]:
                """Transcribe a single chunk and return its index and transcription."""
                logger.info(f"Transcribing chunk {index+1}/{len(chunk_files)}")
                chunk_transcription = await self._transcribe_audio_direct(
                    chunk_file,
                    language=language,
                    prompt=prompt,
                    temperature=temperature
                )
                logger.info(f"Chunk {index+1} transcribed: {len(chunk_transcription)} characters")
                return (index, chunk_transcription)

            # Run all transcriptions concurrently
            transcription_tasks = [
                transcribe_chunk(i, chunk_file)
                for i, chunk_file in enumerate(chunk_files)
            ]
            results = await asyncio.gather(*transcription_tasks)

            # Sort results by index to maintain chunk order
            results.sort(key=lambda x: x[0])
            transcriptions = [text for _, text in results]

            # Assemble full transcription
            full_transcription = " ".join(transcriptions)

            logger.info(
                f"Successfully transcribed chunked audio: "
                f"{len(chunk_files)} chunks, {len(full_transcription)} total characters"
            )

            return full_transcription.strip()

        except AudioChunkingError as e:
            raise TranscriptionError(f"Audio chunking failed: {str(e)}")
        except TranscriptionError:
            raise
        except Exception as e:
            raise TranscriptionError(f"Chunked transcription failed: {str(e)}")
        finally:
            # Clean up chunk files
            if chunk_files:
                logger.info(f"Cleaning up {len(chunk_files)} chunk files")
                AudioChunker.cleanup_chunks(chunk_files)

    def _transcribe_sync(self, params: dict) -> str:
        """Synchronous transcription call."""
        try:
            response = self.client.audio.transcriptions.create(**params)
            # Handle both text response and object response
            if isinstance(response, str):
                return response
            elif hasattr(response, 'text'):
                return response.text
            else:
                return str(response)
        finally:
            # Ensure file is closed
            if 'file' in params:
                params['file'].close()

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using OpenAI.

        Args:
            text: Text to generate embedding for

        Returns:
            List of floats representing the embedding vector

        Raises:
            EmbeddingError: If embedding generation fails
        """
        try:
            # Validate input
            if not text or not text.strip():
                raise EmbeddingError("Empty text provided for embedding")

            # Truncate text if too long (OpenAI has token limits)
            text = self._truncate_text_for_embedding(text.strip())

            # Generate embedding
            response = await self.async_client.embeddings.create(
                model=self.settings.openai_model_embedding,
                input=text,
                encoding_format="float"
            )

            # Extract embedding from response
            embedding = response.data[0].embedding

            # Validate embedding
            if not embedding or len(embedding) == 0:
                raise EmbeddingError("Empty embedding returned from OpenAI")

            logger.info(f"Generated embedding: {len(embedding)} dimensions")
            return embedding

        except EmbeddingError:
            raise
        except Exception as e:
            error_msg = str(e)

            # Handle specific OpenAI errors
            if "rate limit" in error_msg.lower():
                raise EmbeddingError(f"Rate limit exceeded: {error_msg}")
            elif "authentication" in error_msg.lower():
                raise EmbeddingError(f"Authentication failed: {error_msg}")
            elif "token" in error_msg.lower() and "limit" in error_msg.lower():
                raise EmbeddingError(f"Text too long: {error_msg}")
            else:
                raise EmbeddingError(f"Embedding generation failed: {error_msg}")

    def _truncate_text_for_embedding(self, text: str, max_tokens: int = 8000) -> str:
        """Truncate text to fit within token limits."""
        # Rough estimate: 1 token ≈ 4 characters for English text
        max_chars = max_tokens * 4

        if len(text) <= max_chars:
            return text

        # Truncate at word boundary
        truncated = text[:max_chars]
        last_space = truncated.rfind(' ')
        if last_space > max_chars * 0.8:  # Don't cut too much
            truncated = truncated[:last_space]

        logger.warning(f"Text truncated from {len(text)} to {len(truncated)} characters")
        return truncated

    async def generate_summary(
        self,
        transcription: str,
        instructions: Optional[str] = None,
        max_length: int = 75
    ) -> str:
        """
        Generate a summary of the transcription using OpenAI.

        Args:
            transcription: Text to summarize
            instructions: Custom instructions for summarization
            max_length: Maximum length of summary in words

        Returns:
            Generated summary

        Raises:
            SummaryError: If summary generation fails
        """
        try:
            # Validate input
            if not transcription or not transcription.strip():
                raise SummaryError("Empty transcription provided for summary")

            # Skip summarization for very short text
            word_count = len(transcription.split())
            if word_count < 20:
                logger.info("Transcription too short for summarization, returning original")
                return transcription.strip()

            # Prepare system prompt
            system_prompt = self._build_summary_prompt(instructions, max_length)

            # Generate summary
            response = await self.async_client.chat.completions.create(
                model=self.settings.openai_model_chat,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Transcription to summarize:\n\n{transcription}"}
                ],
                temperature=0.1,
                max_tokens=max_length * 2  # Allow some buffer for token count
            )

            # Extract summary
            summary = response.choices[0].message.content

            # Validate result
            if not summary or not summary.strip():
                raise SummaryError("Empty summary returned from OpenAI")

            summary = summary.strip()
            logger.info(f"Generated summary: {len(summary)} characters from {len(transcription)} character transcription")
            return summary

        except SummaryError:
            raise
        except Exception as e:
            error_msg = str(e)

            # Handle specific OpenAI errors
            if "rate limit" in error_msg.lower():
                raise SummaryError(f"Rate limit exceeded: {error_msg}")
            elif "authentication" in error_msg.lower():
                raise SummaryError(f"Authentication failed: {error_msg}")
            elif "token" in error_msg.lower() and "limit" in error_msg.lower():
                raise SummaryError(f"Text too long for summarization: {error_msg}")
            else:
                raise SummaryError(f"Summary generation failed: {error_msg}")

    def _build_summary_prompt(self, instructions: Optional[str], max_length: int) -> str:
        """Build system prompt for summarization in TNG computer style."""
        base_prompt = (
            "Generate a concise one to two sentence summary of the following ship log transcription."
        )

        if instructions:
            base_prompt += f"Additional parameters: {instructions}\n\n"

        base_prompt += "Return summary content only."

        return base_prompt

    async def classify_log_type(self, transcription: str) -> str:
        """
        Classify log entry as PERSONAL or SHIP based on transcription.

        Uses LLM to determine if this is a personal log. Most logs are NOT personal logs,
        but in the case that they are we treat them differently.

        Args:
            transcription: Transcribed text to classify

        Returns:
            "PERSONAL" or "SHIP" (defaults to "SHIP" if uncertain)

        Raises:
            ClassificationError: If classification fails
        """
        try:
            # Validate input
            if not transcription or not transcription.strip():
                raise ClassificationError("Empty transcription provided for classification")

            # System prompt for pessimistic boolean check
            system_prompt = (
                "Most logs are NOT personal logs, but in the case that they are we treat them differently. "
                "Given this content from the log, is it a personal log? "
                "A personal log is explicitly identified by the speaker saying 'personal log'. "
                "Return ONLY 'True' if it's a personal log, or 'False' if it's not. "
                "Nothing else - just True or False."
            )

            # Use LLM to classify
            response = await self.async_client.chat.completions.create(
                model=self.settings.openai_model_chat,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcription}
                ],
                temperature=0.0,  # Deterministic classification
                max_tokens=5  # Very short response needed
            )

            # Extract classification
            result = response.choices[0].message.content.strip()

            # Parse the boolean response
            is_personal = result.lower() in ['true', 'yes', '1']

            classification = "PERSONAL" if is_personal else "SHIP"
            logger.info(f"Classified log as: {classification} (LLM returned: {result})")
            return classification

        except ClassificationError:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Log classification failed: {error_msg}")
            # Default to SHIP on error
            return "SHIP"

    async def get_token_count(self, text: str) -> int:
        """
        Estimate token count for text (approximate).

        Args:
            text: Text to count tokens for

        Returns:
            Approximate token count
        """
        # Very rough approximation: 1 token ≈ 4 characters for English
        # For more accurate counting, you'd need tiktoken library
        return len(text) // 4

    async def health_check(self) -> bool:
        """
        Check if OpenAI API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Try a minimal API call to test connectivity
            await self.async_client.models.list()
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False