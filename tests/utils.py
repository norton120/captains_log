"""Test utilities and helpers."""
import asyncio
import tempfile
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import MagicMock
import numpy as np


def create_mock_audio_file(
    duration_seconds: float = 1.0, 
    sample_rate: int = 44100,
    format: str = "wav"
) -> Path:
    """Create a mock audio file for testing."""
    # Create a minimal WAV file with actual audio data
    import wave
    import struct
    
    with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as tmp_file:
        if format.lower() == "wav":
            # Create proper WAV file
            frames = int(duration_seconds * sample_rate)
            with wave.open(tmp_file.name, 'w') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                
                # Generate sine wave
                for i in range(frames):
                    value = int(32767 * np.sin(2 * np.pi * 440 * i / sample_rate))
                    wav_file.writeframes(struct.pack('<h', value))
        else:
            # For other formats, just write some binary data
            tmp_file.write(b"fake audio data" * 1000)
        
        return Path(tmp_file.name)


def create_large_audio_file(size_mb: int = 15) -> Path:
    """Create a large audio file for testing size limits."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        chunk_size = 1024  # 1KB chunks
        total_chunks = size_mb * 1024
        
        for _ in range(total_chunks):
            tmp_file.write(b"x" * chunk_size)
        
        return Path(tmp_file.name)


def assert_embeddings_similar(embedding1: List[float], embedding2: List[float], threshold: float = 0.8):
    """Assert that two embeddings are similar based on cosine similarity."""
    import numpy as np
    
    # Convert to numpy arrays
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    # Calculate cosine similarity
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    cosine_sim = dot_product / (norm1 * norm2)
    
    assert cosine_sim >= threshold, f"Embeddings not similar enough: {cosine_sim} < {threshold}"


class MockOpenAIResponse:
    """Mock OpenAI API response structures."""
    
    @staticmethod
    def transcription_response(text: str):
        """Create mock transcription response."""
        mock = MagicMock()
        mock.text = text
        return mock
    
    @staticmethod
    def embedding_response(embedding: List[float]):
        """Create mock embedding response."""
        mock = MagicMock()
        mock.data = [MagicMock(embedding=embedding)]
        return mock
    
    @staticmethod
    def chat_response(content: str):
        """Create mock chat completion response."""
        mock = MagicMock()
        mock.choices = [MagicMock(message=MagicMock(content=content))]
        return mock


class AsyncContextManager:
    """Helper for creating async context managers in tests."""
    
    def __init__(self, return_value=None):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def run_async_test(coro):
    """Helper to run async test functions."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAudioFiles:
    """Pre-defined test audio files for different scenarios."""
    
    SAMPLE_TRANSCRIPTION = "This is a sample captain's log entry for testing purposes."
    LONG_TRANSCRIPTION = " ".join([SAMPLE_TRANSCRIPTION] * 20)  # Long text for summarization
    SHORT_TRANSCRIPTION = "Hi."
    
    EXPECTED_SUMMARY = "Brief summary of the captain's log entry."
    EXPECTED_EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small dimension


def cleanup_test_files(*file_paths: Path):
    """Clean up test files after use."""
    for file_path in file_paths:
        if file_path.exists():
            file_path.unlink()


def mock_async_function(return_value=None, side_effect=None):
    """Create a mock async function."""
    mock = MagicMock()
    
    async def async_mock(*args, **kwargs):
        if side_effect:
            if callable(side_effect):
                return side_effect(*args, **kwargs)
            else:
                raise side_effect
        return return_value
    
    mock.side_effect = async_mock
    return mock