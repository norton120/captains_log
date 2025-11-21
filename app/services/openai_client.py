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
    
    def _validate_audio_file(self, audio_file: Path) -> None:
        """Validate audio file for transcription."""
        if not audio_file.exists():
            raise TranscriptionError(f"Audio file not found: {audio_file}")
        
        # Check file size (use configured max size, default OpenAI limit is 25MB)
        file_size = audio_file.stat().st_size
        max_size = min(self.settings.max_audio_file_size, 25 * 1024 * 1024)  # Use settings or 25MB limit
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            raise TranscriptionError(f"File too large: {size_mb:.1f}MB > {max_mb:.1f}MB")
        
        # Check file format
        allowed_extensions = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
        if audio_file.suffix.lower() not in allowed_extensions:
            raise TranscriptionError(
                f"Unsupported audio format: {audio_file.suffix}. "
                f"Allowed formats: {', '.join(allowed_extensions)}"
            )
    
    async def transcribe_audio(
        self, 
        audio_file: Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """
        Transcribe audio file using OpenAI Whisper.
        
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
            # Validate audio file
            self._validate_audio_file(audio_file)
            
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
        
        finally:
            # Ensure file is closed
            try:
                if 'transcription_params' in locals() and 'file' in transcription_params:
                    transcription_params['file'].close()
            except:
                pass
    
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
            "Generate ship log summary in Starfleet computer format. "
            f"Maximum {max_length} words. Use precise, clinical language. "
            "Report critical events, environmental conditions, and navigation status. "
            "No contractions. No emotional language. State facts only. "
            "Use terminology: position, heading, environmental systems, structural integrity, operations. "
            "Format: Status reports and operational summaries.\n\n"
        )
        
        if instructions:
            base_prompt += f"Additional parameters: {instructions}\n\n"
        
        base_prompt += "Return summary data only."
        
        return base_prompt
    
    async def classify_log_type(self, transcription: str) -> str:
        """
        Classify log entry as PERSONAL or SHIP based on transcription.
        
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
            
            # Get first few lines for classification
            lines = transcription.strip().split('\n')
            first_lines = '\n'.join(lines[:3]).strip()  # Use first 3 lines
            
            # System prompt for classification
            system_prompt = (
                "Classify this log entry as either 'PERSONAL' or 'SHIP' based ONLY on the opening words. "
                "Look for these exact patterns:\n"
                "- PERSONAL: starts with 'Personal log', 'personal log', or similar personal indicators\n"
                "- SHIP: starts with 'Captain's log', 'Ship's log', 'Science Officer's log', 'Chief Engineer's log', "
                "'First Officer's log', 'Medical log', or any other ship/crew role log\n\n"
                "Rules:\n"
                "1. If it starts with 'Personal log' (any capitalization), return 'PERSONAL'\n"
                "2. If it starts with any ship/crew role + 'log', return 'SHIP'\n"
                "3. If uncertain or no clear pattern, default to 'SHIP'\n"
                "4. Return ONLY the word 'PERSONAL' or 'SHIP', nothing else"
            )
            
            # Generate classification
            response = await self.async_client.chat.completions.create(
                model=self.settings.openai_model_chat,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this log opening:\n\n{first_lines}"}
                ],
                temperature=0.0,  # Deterministic classification
                max_tokens=10  # Very short response needed
            )
            
            # Extract classification
            classification = response.choices[0].message.content.strip().upper()
            
            # Validate result
            if classification not in ["PERSONAL", "SHIP"]:
                logger.warning(f"Invalid classification '{classification}', defaulting to SHIP")
                return "SHIP"
            
            logger.info(f"Classified log as: {classification}")
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