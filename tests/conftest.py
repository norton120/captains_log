"""Test configuration and fixtures."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from fastapi import UploadFile
import httpx
import vcr
from moto import mock_aws
import boto3
import io

# Add the parent directory to the Python path for Docker environment
current_dir = Path(__file__).parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from app.config import Settings
from app.models.log_entry import Base, LogEntry, ProcessingStatus
from app.main import app


# Test Settings
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test-specific settings."""
    return Settings(
        app_name="Captain's Log Test",
        debug=True,
        database_url="sqlite+aiosqlite:///:memory:",
        openai_api_key="test-key-12345",
        s3_bucket_name="test-captains-log-bucket",
        aws_region="us-east-1",
        dbos_app_name="captains-log-test",
        max_audio_file_size=2 * 1024 * 1024,  # 2MB for tests to make oversized test work
    )


# Database fixtures
@pytest_asyncio.fixture(scope="function")
async def async_db_engine(test_settings):
    """Create async test database engine."""
    engine = create_async_engine(
        test_settings.database_url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=test_settings.debug,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_db_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for tests."""
    async_session = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session


# Mock external services
@pytest.fixture(scope="function")
def mock_s3_service():
    """Mock S3 service for testing."""
    with mock_aws():
        # Create test bucket
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket="test-captains-log-bucket")
        yield s3_client


@pytest.fixture(scope="function")
def mock_openai_client():
    """Mock OpenAI client for testing."""
    mock_client = MagicMock()
    
    # Mock transcription response
    mock_transcription = MagicMock()
    mock_transcription.text = "This is a test transcription of the audio file."
    mock_client.audio.transcriptions.create.return_value = mock_transcription
    
    # Mock embedding response
    mock_embedding = MagicMock()
    mock_embedding.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_embedding
    
    # Mock chat completion response
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Test summary"))]
    mock_client.chat.completions.create.return_value = mock_completion
    
    return mock_client


@pytest.fixture(scope="function")
def mock_async_openai_client():
    """Mock async OpenAI client for testing."""
    mock_client = AsyncMock()
    
    # Mock embedding response
    mock_embedding = MagicMock()
    mock_embedding.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_embedding
    
    # Mock chat completion response  
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Test summary"))]
    mock_client.chat.completions.create.return_value = mock_completion
    
    # Mock models list for health check
    mock_client.models.list.return_value = MagicMock()
    
    return mock_client


# VCR fixtures for recording real API calls
@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration for recording API calls."""
    return {
        "filter_headers": ["authorization", "x-api-key"],
        "filter_post_data_parameters": ["api_key"],
        "record_mode": "once",
        "match_on": ["uri", "method"],
        "cassette_library_dir": "tests/cassettes",
    }


@pytest.fixture(scope="function")
def vcr_cassette(request, vcr_config):
    """Create VCR cassette for individual test."""
    cassette_name = f"{request.module.__name__}.{request.function.__name__}"
    with vcr.use_cassette(f"{cassette_name}.yaml", **vcr_config) as cassette:
        yield cassette


# Test data fixtures
@pytest.fixture(scope="session")
def sample_audio_file() -> Generator[Path, None, None]:
    """Create a sample audio file for testing."""
    # Create a minimal WAV file (44 bytes of silence)
    wav_header = bytes([
        0x52, 0x49, 0x46, 0x46,  # "RIFF"
        0x24, 0x00, 0x00, 0x00,  # File size - 8
        0x57, 0x41, 0x56, 0x45,  # "WAVE"
        0x66, 0x6D, 0x74, 0x20,  # "fmt "
        0x10, 0x00, 0x00, 0x00,  # Subchunk1 size
        0x01, 0x00,              # Audio format (PCM)
        0x01, 0x00,              # Channels (1)
        0x44, 0xAC, 0x00, 0x00,  # Sample rate (44100)
        0x88, 0x58, 0x01, 0x00,  # Byte rate
        0x02, 0x00,              # Block align
        0x10, 0x00,              # Bits per sample (16)
        0x64, 0x61, 0x74, 0x61,  # "data"
        0x00, 0x00, 0x00, 0x00,  # Data size (0)
    ])
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_file.write(wav_header)
        tmp_file.flush()
        yield Path(tmp_file.name)
    
    # Cleanup
    os.unlink(tmp_file.name)


@pytest.fixture(scope="session")
def large_audio_file() -> Generator[Path, None, None]:
    """Create a large audio file for testing size limits."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        # Write 15MB of data to exceed 10MB test limit
        chunk = b"x" * 1024  # 1KB chunk
        for _ in range(15 * 1024):  # 15MB total
            tmp_file.write(chunk)
        tmp_file.flush()
        yield Path(tmp_file.name)
    
    # Cleanup
    os.unlink(tmp_file.name)


# FastAPI test client
@pytest.fixture(scope="function")
def test_client(test_settings, async_db_session):
    """Create test client for API testing."""
    # Override dependencies
    app.dependency_overrides = {}
    
    with TestClient(app) as client:
        yield client


# Log entry factories
@pytest_asyncio.fixture
async def log_entry_factory(async_db_session):
    """Factory for creating test log entries."""
    created_entries = []
    
    async def _create_log_entry(
        audio_s3_key: str = "test/audio.wav",
        audio_local_path: str = None,
        transcription: str = None,
        summary: str = None,
        processing_status: ProcessingStatus = ProcessingStatus.PENDING,
        processing_error: str = None,
    ) -> LogEntry:
        entry = LogEntry(
            audio_s3_key=audio_s3_key,
            audio_local_path=audio_local_path,
            transcription=transcription,
            summary=summary,
            processing_status=processing_status,
            processing_error=processing_error,
        )
        async_db_session.add(entry)
        await async_db_session.commit()
        await async_db_session.refresh(entry)
        created_entries.append(entry)
        return entry
    
    yield _create_log_entry
    
    # Cleanup
    for entry in created_entries:
        await async_db_session.delete(entry)
    await async_db_session.commit()


# Workflow mocks
@pytest.fixture(scope="function")
def mock_dbos_workflow():
    """Mock DBOS workflow for testing."""
    mock_workflow = AsyncMock()
    mock_workflow.workflow_uuid = "test-workflow-123"
    mock_workflow.status = "PENDING"
    return mock_workflow


# Test directory setup
@pytest.fixture(autouse=True, scope="session")
def setup_test_directories():
    """Ensure test directories exist."""
    test_dirs = [
        "tests/cassettes",
        "tests/fixtures",
        "tests/temp",
    ]
    
    for directory in test_dirs:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    yield
    
    # Optional: cleanup test directories if needed
    # for directory in test_dirs:
    #     shutil.rmtree(directory, ignore_errors=True)


# Event loop configuration for tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# API Test Fixtures
@pytest.fixture(scope="function")
def audio_test_files():
    """Provide paths to test audio files."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    return {
        "valid_short": fixtures_dir / "test_audio_short.wav",
        "valid_medium": fixtures_dir / "test_audio_medium.wav", 
        "valid_long": fixtures_dir / "test_audio_long.wav",
        "valid_tiny": fixtures_dir / "test_audio_tiny.wav",
        "oversized": fixtures_dir / "test_audio_large.wav",
        "empty": fixtures_dir / "empty_file.wav",
        "corrupted": fixtures_dir / "corrupted_audio.wav",
    }


@pytest.fixture(scope="function")  
def upload_file_factory(audio_test_files):
    """Factory for creating mock file uploads."""
    
    def _create_upload_file(
        file_key: str = "valid_short",
        filename: str = None,
        content_type: str = "audio/wav"
    ) -> UploadFile:
        """Create a mock UploadFile for testing."""
        file_path = audio_test_files[file_key]
        
        if filename is None:
            filename = file_path.name
            
        # Read file content into bytes
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        # Create BytesIO object
        file_obj = io.BytesIO(file_content)
        file_obj.name = filename
        
        # Create UploadFile
        upload_file = UploadFile(
            file=file_obj,
            filename=filename,
            headers={"content-type": content_type},
            size=len(file_content)
        )
        
        return upload_file
    
    return _create_upload_file


@pytest.fixture(scope="function")
def multipart_form_data(upload_file_factory):
    """Create multipart form data for file upload tests."""
    
    def _create_form_data(file_key: str = "valid_short", **extra_data):
        """Create form data dict for multipart uploads."""
        upload_file = upload_file_factory(file_key)
        
        form_data = {"file": upload_file}
        form_data.update(extra_data)
        
        return form_data
    
    return _create_form_data


@pytest_asyncio.fixture(scope="function") 
async def api_client(test_settings, async_db_engine):
    """Async HTTP client for API testing."""
    from app.main import app
    from app.dependencies import get_settings, get_db_session
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    
    # Create session maker for API testing
    async_session_maker = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async def override_get_db_session():
        async with async_session_maker() as session:
            yield session
    
    # Override dependencies for testing
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = override_get_db_session
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
    
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def mock_background_tasks():
    """Mock FastAPI background tasks."""
    mock_tasks = MagicMock()
    mock_tasks.add_task = MagicMock()
    return mock_tasks


@pytest.fixture(scope="function")
def mock_workflow_service():
    """Mock audio processing workflow service."""
    mock_service = AsyncMock()
    mock_service.process_audio.return_value = {
        "workflow_id": "test-workflow-123",
        "status": "started",
        "log_entry_id": "test-log-entry-456"
    }
    return mock_service