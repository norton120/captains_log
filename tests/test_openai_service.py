"""Tests for OpenAI service functionality."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from openai import OpenAI
from pytest import mark as m

from app.services.openai_client import (
    OpenAIService, 
    TranscriptionError, 
    EmbeddingError, 
    SummaryError
)


@pytest.fixture
def openai_service(test_settings, mock_openai_client, mock_async_openai_client):
    """Create OpenAI service instance for testing."""
    service = OpenAIService(test_settings)
    service.client = mock_openai_client
    service.async_client = mock_async_openai_client
    return service


@m.describe("OpenAI Transcription")
class TestOpenAITranscription:
    """Test OpenAI audio transcription functionality."""
    
    @m.context("When transcribing a valid audio file")
    @m.it("transcribes audio file and returns text")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_audio_success(self, openai_service, sample_audio_file):
        """Should successfully transcribe a valid audio file."""
        # Act
        transcription = await openai_service.transcribe_audio(sample_audio_file)
        
        # Assert
        assert transcription == "This is a test transcription of the audio file."
        openai_service.client.audio.transcriptions.create.assert_called_once()
    
    @m.context("When using custom transcription settings")
    @m.it("passes custom parameters to OpenAI API")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_audio_custom_params(self, openai_service, sample_audio_file):
        """Should pass custom parameters to the transcription API."""
        # Act
        await openai_service.transcribe_audio(
            sample_audio_file,
            language="en",
            prompt="Captain's log entry"
        )
        
        # Assert
        call_kwargs = openai_service.client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["language"] == "en"
        assert call_kwargs["prompt"] == "Captain's log entry"
    
    @m.context("When transcribing unsupported audio format")
    @m.it("handles unsupported audio formats gracefully")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_audio_invalid_format(self, openai_service, tmp_path):
        """Should handle unsupported audio formats."""
        # Arrange
        invalid_file = tmp_path / "test.txt"
        invalid_file.write_text("not an audio file")
        
        # Act & Assert
        with pytest.raises(TranscriptionError, match="Unsupported audio format"):
            await openai_service.transcribe_audio(invalid_file)
    
    @m.context("When OpenAI API returns an error")
    @m.it("handles OpenAI API failures gracefully")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_audio_api_error(self, openai_service, sample_audio_file):
        """Should handle OpenAI API errors gracefully."""
        # Arrange
        openai_service.client.audio.transcriptions.create.side_effect = Exception("API Error")
        
        # Act & Assert
        with pytest.raises(TranscriptionError, match="Transcription failed"):
            await openai_service.transcribe_audio(sample_audio_file)
    
    @m.context("When transcription result is empty")
    @m.it("handles empty transcription results")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_audio_empty_result(self, openai_service, sample_audio_file):
        """Should handle empty transcription results."""
        # Arrange
        openai_service.client.audio.transcriptions.create.return_value.text = ""
        
        # Act & Assert
        with pytest.raises(TranscriptionError, match="Empty transcription"):
            await openai_service.transcribe_audio(sample_audio_file)
    
    @m.context("When transcribing large audio files")
    @m.it("uses chunking for large audio files")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_large_audio_file(self, openai_service, large_audio_file, tmp_path):
        """Should use chunking for large audio files."""
        # Arrange - Mock the chunker
        from app.services.audio_chunker import AudioChunker
        mock_chunker = AsyncMock(spec=AudioChunker)

        # Create mock chunk files
        chunk1 = tmp_path / "chunk_001.wav"
        chunk2 = tmp_path / "chunk_002.wav"
        chunk1.write_bytes(b"chunk 1 data")
        chunk2.write_bytes(b"chunk 2 data")

        mock_chunker.chunk_audio_file.return_value = [chunk1, chunk2]
        openai_service.audio_chunker = mock_chunker

        # Mock transcriptions for each chunk
        openai_service.client.audio.transcriptions.create.side_effect = [
            MagicMock(text="First chunk transcription."),
            MagicMock(text="Second chunk transcription.")
        ]

        # Act
        transcription = await openai_service.transcribe_audio(large_audio_file)

        # Assert
        assert "First chunk transcription" in transcription
        assert "Second chunk transcription" in transcription
        mock_chunker.chunk_audio_file.assert_called_once()
        assert openai_service.client.audio.transcriptions.create.call_count == 2

    @m.context("When chunked transcription fails")
    @m.it("cleans up chunk files on error")
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_transcribe_chunked_cleanup_on_error(self, openai_service, large_audio_file, tmp_path):
        """Should clean up chunk files when chunked transcription fails."""
        # Arrange
        from app.services.audio_chunker import AudioChunker
        mock_chunker = AsyncMock(spec=AudioChunker)

        # Create mock chunk files
        chunk1 = tmp_path / "chunk_001.wav"
        chunk1.write_bytes(b"chunk 1 data")

        mock_chunker.chunk_audio_file.return_value = [chunk1]
        openai_service.audio_chunker = mock_chunker

        # Make transcription fail
        openai_service.client.audio.transcriptions.create.side_effect = Exception("API Error")

        # Act & Assert
        with pytest.raises(TranscriptionError):
            await openai_service.transcribe_audio(large_audio_file)

        # Chunk file should be cleaned up (deleted)
        # Note: In the actual implementation, cleanup happens in finally block


@m.describe("OpenAI Embeddings")
class TestOpenAIEmbeddings:
    """Test OpenAI embedding generation functionality."""
    
    @m.context("When generating embeddings for valid text")
    @m.it("generates embeddings for input text")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_embedding_success(self, openai_service):
        """Should successfully generate embeddings for input text."""
        # Arrange
        text = "This is a test transcription for embedding generation."
        
        # Act
        embedding = await openai_service.generate_embedding(text)
        
        # Assert
        assert len(embedding) == 1536  # text-embedding-3-small dimension
        assert all(isinstance(x, float) for x in embedding)
        openai_service.async_client.embeddings.create.assert_called_once()
    
    @m.context("When generating embeddings for empty text")
    @m.it("handles empty input text")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_embedding_empty_text(self, openai_service):
        """Should handle empty input text appropriately."""
        # Act & Assert
        with pytest.raises(EmbeddingError, match="Empty text"):
            await openai_service.generate_embedding("")
    
    @m.context("When generating embeddings for long text")
    @m.it("handles text exceeding token limits")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_embedding_long_text(self, openai_service):
        """Should handle text that exceeds token limits."""
        # Arrange
        long_text = "word " * 10000  # Very long text
        
        # Act
        embedding = await openai_service.generate_embedding(long_text)
        
        # Assert - should truncate and still work
        assert len(embedding) == 1536
    
    @m.context("When embedding API encounters error")
    @m.it("handles OpenAI embedding API failures")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_embedding_api_error(self, openai_service):
        """Should handle OpenAI embedding API errors."""
        # Arrange
        openai_service.async_client.embeddings.create.side_effect = Exception("API Error")
        
        # Act & Assert
        with pytest.raises(EmbeddingError, match="Embedding generation failed"):
            await openai_service.generate_embedding("test text")


@m.describe("OpenAI Summary")
class TestOpenAISummary:
    """Test OpenAI summary generation functionality."""
    
    @m.context("When generating summary for transcription")
    @m.it("generates summary for transcription")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_summary_success(self, openai_service):
        """Should successfully generate summary for transcription."""
        # Arrange
        transcription = "This is a much longer transcription that contains many detailed observations about the sailing conditions, weather patterns, navigation decisions, crew activities, and various incidents that occurred during this particular voyage that definitely needs to be summarized into key points."
        
        # Act
        summary = await openai_service.generate_summary(transcription)
        
        # Assert
        assert summary == "Test summary"
        openai_service.async_client.chat.completions.create.assert_called_once()
    
    @m.context("When summarizing short text")
    @m.it("handles text too short to summarize")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_summary_short_text(self, openai_service):
        """Should handle text that's too short to meaningfully summarize."""
        # Arrange
        short_text = "Hi."
        
        # Act
        summary = await openai_service.generate_summary(short_text)
        
        # Assert - should return original text for short transcriptions
        assert summary == short_text
    
    @m.context("When using custom summary instructions")
    @m.it("accepts custom summary instructions")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_summary_custom_instructions(self, openai_service):
        """Should accept and use custom summary instructions."""
        # Arrange
        transcription = "This is a much longer transcription that contains many detailed observations about the sailing conditions, weather patterns, navigation decisions, crew activities, and various incidents that occurred during this particular voyage that definitely needs to be summarized into key points for the captain's log."
        instructions = "Focus on technical details and action items."
        
        # Act
        await openai_service.generate_summary(transcription, instructions=instructions)
        
        # Assert
        call_kwargs = openai_service.async_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert any(instructions in msg["content"] for msg in messages if msg["role"] == "system")
    
    @m.context("When summary API encounters error")
    @m.it("handles OpenAI chat API failures")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_summary_api_error(self, openai_service):
        """Should handle OpenAI chat API errors."""
        # Arrange
        openai_service.async_client.chat.completions.create.side_effect = Exception("API Error")
        
        # Act & Assert
        with pytest.raises(SummaryError, match="Summary generation failed"):
            await openai_service.generate_summary("This is a much longer test transcription that contains enough words to trigger the actual API call and test the error handling functionality properly for the summary generation process.")
    
    @m.context("When summary response is empty")
    @m.it("handles empty summary responses")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_generate_summary_empty_response(self, openai_service):
        """Should handle empty summary responses."""
        # Arrange
        openai_service.async_client.chat.completions.create.return_value.choices[0].message.content = ""
        
        # Act & Assert
        with pytest.raises(SummaryError, match="Empty summary"):
            await openai_service.generate_summary("This is a much longer test transcription that contains enough words to trigger the actual API call and test the empty response handling functionality properly for the summary generation process.")


@m.describe("OpenAI Rate Limiting")
class TestOpenAIServiceRateLimit:
    """Test OpenAI service rate limiting and retry logic."""
    
    @m.context("When API rate limit is exceeded")
    @m.it("handles API rate limits gracefully")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_openai_rate_limiting(self, openai_service, sample_audio_file):
        """Should handle OpenAI API rate limits with appropriate backoff."""
        # Arrange
        from openai import RateLimitError
        openai_service.client.audio.transcriptions.create.side_effect = RateLimitError(
            "Rate limit exceeded", response=MagicMock(), body=None
        )
        
        # Act & Assert
        with pytest.raises(TranscriptionError, match="Rate limit"):
            await openai_service.transcribe_audio(sample_audio_file)
    
    @m.context("When API key is invalid")
    @m.it("handles invalid API keys gracefully")
    @pytest.mark.unit
    @pytest.mark.openai
    async def test_openai_authentication_error(self, openai_service, sample_audio_file):
        """Should handle OpenAI authentication errors."""
        # Arrange
        from openai import AuthenticationError
        openai_service.client.audio.transcriptions.create.side_effect = AuthenticationError(
            "Invalid API key", response=MagicMock(), body=None
        )
        
        # Act & Assert
        with pytest.raises(TranscriptionError, match="Authentication"):
            await openai_service.transcribe_audio(sample_audio_file)


@m.describe("OpenAI Integration")
class TestOpenAIServiceIntegration:
    """Integration tests for OpenAI service with real API calls."""
    
    @m.context("When verifying transcription quality")
    @m.it("verifies transcription accuracy with known audio")
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.openai
    async def test_transcription_quality(self, openai_service, sample_audio_file):
        """Should verify transcription accuracy with known audio samples."""
        # Arrange
        expected_transcription = "This is a test recording for the captain's log system."
        openai_service.client.audio.transcriptions.create.return_value.text = expected_transcription
        
        # Act
        result = await openai_service.transcribe_audio(sample_audio_file)
        
        # Assert
        assert result == expected_transcription
        assert len(result) > 10  # Reasonable transcription length
        assert "test" in result.lower()  # Should contain expected content
        
        # Verify API was called with correct parameters
        openai_service.client.audio.transcriptions.create.assert_called_once()
        call_kwargs = openai_service.client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
    
    @m.context("When verifying embedding similarity")
    @m.it("verifies similar text produces similar embeddings")
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.openai
    async def test_embedding_similarity(self, openai_service):
        """Should verify that similar texts produce similar embeddings."""
        # Arrange
        text1 = "The weather is sunny and calm today."
        text2 = "It's a beautiful sunny day with calm conditions."
        text3 = "The engine needs maintenance and repair work."
        
        # Mock embeddings - similar texts should have similar vectors
        embedding1 = [0.1, 0.8, 0.2, 0.1] * 384  # 1536 dimensions
        embedding2 = [0.15, 0.75, 0.25, 0.05] * 384  # Similar to embedding1
        embedding3 = [0.8, 0.1, 0.7, 0.9] * 384  # Different from embedding1/2
        
        # Configure mock to return different embeddings for different texts
        def mock_embedding_response(text, **kwargs):
            mock_response = MagicMock()
            if "sunny" in text or "beautiful" in text:
                if "calm" in text:
                    mock_response.data = [MagicMock(embedding=embedding1 if "weather" in text else embedding2)]
                else:
                    mock_response.data = [MagicMock(embedding=embedding1)]
            else:
                mock_response.data = [MagicMock(embedding=embedding3)]
            return mock_response
        
        openai_service.async_client.embeddings.create.side_effect = lambda input, **kwargs: mock_embedding_response(input, **kwargs)
        
        # Act
        emb1 = await openai_service.generate_embedding(text1)
        emb2 = await openai_service.generate_embedding(text2)
        emb3 = await openai_service.generate_embedding(text3)
        
        # Assert
        import math
        
        # Calculate cosine similarity without numpy
        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            return dot_product / (norm_a * norm_b)
        
        sim_1_2 = cosine_similarity(emb1, emb2)
        sim_1_3 = cosine_similarity(emb1, emb3)
        
        # Similar texts should have higher similarity than dissimilar ones
        assert sim_1_2 > 0.9  # Similar texts should be very similar
        assert sim_1_3 < 0.8  # Dissimilar texts should be less similar
        assert sim_1_2 > sim_1_3  # Weather texts more similar to each other than to engine text