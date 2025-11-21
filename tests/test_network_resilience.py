"""Tests for network resilience functionality."""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import tempfile
from uuid import uuid4

from app.services.network_resilient_processor import (
    NetworkResilientProcessor, 
    NetworkTask, 
    TaskType, 
    TaskPriority
)
from app.config import Settings
from app.services.s3 import AudioUploadError
from app.services.openai_client import TranscriptionError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        openai_api_key="test_key",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
        s3_bucket_name="test-bucket"
    )


@pytest.fixture
async def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
async def resilient_processor(mock_settings, mock_db_session):
    """Create resilient processor for testing."""
    processor = NetworkResilientProcessor(
        settings=mock_settings,
        db_session=mock_db_session
    )
    return processor


class TestNetworkTask:
    """Test NetworkTask functionality."""
    
    def test_task_creation(self):
        """Test creating a network task."""
        task = NetworkTask(
            task_id="test_1",
            task_type=TaskType.S3_UPLOAD,
            priority=TaskPriority.HIGH,
            log_entry_id="log_123",
            payload={"file_path": "/tmp/test.wav"}
        )
        
        assert task.task_id == "test_1"
        assert task.task_type == TaskType.S3_UPLOAD
        assert task.priority == TaskPriority.HIGH
        assert task.retry_count == 0
        assert task.should_retry() == True
        assert task.is_completed == False
    
    def test_task_serialization(self):
        """Test task serialization and deserialization."""
        original_task = NetworkTask(
            task_id="test_1",
            task_type=TaskType.TRANSCRIPTION,
            priority=TaskPriority.MEDIUM,
            log_entry_id="log_123",
            payload={"transcription": "test content"}
        )
        
        # Serialize
        task_dict = original_task.to_dict()
        
        # Deserialize
        restored_task = NetworkTask.from_dict(task_dict)
        
        assert restored_task.task_id == original_task.task_id
        assert restored_task.task_type == original_task.task_type
        assert restored_task.priority == original_task.priority
        assert restored_task.payload == original_task.payload
    
    def test_retry_logic(self):
        """Test retry logic and backoff calculation."""
        task = NetworkTask(
            task_id="test_1",
            task_type=TaskType.S3_UPLOAD,
            priority=TaskPriority.HIGH,
            log_entry_id="log_123",
            payload={"file_path": "/tmp/test.wav"},
            max_retries=3
        )
        
        # Initial state
        assert task.should_retry() == True
        
        # Mark first attempt
        task.mark_attempt("Network error")
        assert task.retry_count == 1
        assert task.should_retry() == True  # Still within retry limit
        
        # Mark more attempts
        task.mark_attempt("Still failing")
        task.mark_attempt("Still failing")
        assert task.retry_count == 3
        assert task.should_retry() == False  # Exceeded max retries
    
    def test_task_completion(self):
        """Test marking task as completed."""
        task = NetworkTask(
            task_id="test_1",
            task_type=TaskType.S3_UPLOAD,
            priority=TaskPriority.HIGH,
            log_entry_id="log_123",
            payload={"file_path": "/tmp/test.wav"}
        )
        
        task.mark_completed()
        assert task.is_completed == True
        assert task.should_retry() == False
        assert task.next_retry_at is None


class TestNetworkResilientProcessor:
    """Test NetworkResilientProcessor functionality."""
    
    @pytest.mark.asyncio
    async def test_queue_s3_upload(self, resilient_processor):
        """Test queuing S3 upload task."""
        test_file = Path("/tmp/test.wav")
        log_entry_id = "log_123"
        
        task_id = await resilient_processor.queue_s3_upload(
            log_entry_id, test_file, is_video=False
        )
        
        assert task_id in resilient_processor.task_queue
        task = resilient_processor.task_queue[task_id]
        assert task.task_type == TaskType.S3_UPLOAD
        assert task.log_entry_id == log_entry_id
        assert task.payload["file_path"] == str(test_file)
        assert task.payload["is_video"] == False
    
    @pytest.mark.asyncio
    async def test_queue_transcription(self, resilient_processor):
        """Test queuing transcription task."""
        test_file = Path("/tmp/test.wav")
        log_entry_id = "log_123"
        
        task_id = await resilient_processor.queue_transcription(
            log_entry_id, audio_file=test_file
        )
        
        assert task_id in resilient_processor.task_queue
        task = resilient_processor.task_queue[task_id]
        assert task.task_type == TaskType.TRANSCRIPTION
        assert task.log_entry_id == log_entry_id
        assert task.payload["audio_file"] == str(test_file)
    
    @pytest.mark.asyncio
    async def test_process_s3_upload_success(self, resilient_processor):
        """Test successful S3 upload processing."""
        # Mock S3 service
        resilient_processor.s3_service = AsyncMock()
        resilient_processor.s3_service.upload_audio.return_value = "s3://bucket/audio/test.wav"
        
        # Mock update log entry
        resilient_processor._update_log_entry = AsyncMock()
        
        # Create test file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(b"fake audio data")
            test_file = Path(tmp_file.name)
        
        try:
            # Create task
            task = NetworkTask(
                task_id="test_1",
                task_type=TaskType.S3_UPLOAD,
                priority=TaskPriority.HIGH,
                log_entry_id="log_123",
                payload={"file_path": str(test_file), "is_video": False}
            )
            
            # Process task
            await resilient_processor._execute_s3_upload(task)
            
            # Verify S3 upload was called
            resilient_processor.s3_service.upload_audio.assert_called_once_with(test_file)
            
            # Verify log entry was updated
            resilient_processor._update_log_entry.assert_called_once_with(
                "log_123", {"audio_s3_key": "s3://bucket/audio/test.wav"}
            )
        
        finally:
            # Clean up test file
            test_file.unlink()
    
    @pytest.mark.asyncio
    async def test_process_s3_upload_failure_and_retry(self, resilient_processor):
        """Test S3 upload failure and retry logic."""
        # Mock S3 service to fail initially then succeed
        resilient_processor.s3_service = AsyncMock()
        resilient_processor.s3_service.upload_audio.side_effect = [
            AudioUploadError("Network timeout"),
            "s3://bucket/audio/test.wav"  # Success on second try
        ]
        
        # Mock update log entry
        resilient_processor._update_log_entry = AsyncMock()
        
        # Create test file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(b"fake audio data")
            test_file = Path(tmp_file.name)
        
        try:
            # Create task
            task = NetworkTask(
                task_id="test_1",
                task_type=TaskType.S3_UPLOAD,
                priority=TaskPriority.HIGH,
                log_entry_id="log_123",
                payload={"file_path": str(test_file), "is_video": False}
            )
            
            # First attempt should fail
            with pytest.raises(AudioUploadError):
                await resilient_processor._execute_s3_upload(task)
            
            # Second attempt should succeed
            await resilient_processor._execute_s3_upload(task)
            
            # Verify retry occurred
            assert resilient_processor.s3_service.upload_audio.call_count == 2
        
        finally:
            # Clean up test file
            test_file.unlink()
    
    @pytest.mark.asyncio
    async def test_queue_status(self, resilient_processor):
        """Test getting queue status."""
        # Add some test tasks
        await resilient_processor.queue_s3_upload("log_1", Path("/tmp/test1.wav"))
        await resilient_processor.queue_transcription("log_2", audio_file=Path("/tmp/test2.wav"))
        
        # Mark one as completed
        task_ids = list(resilient_processor.task_queue.keys())
        resilient_processor.task_queue[task_ids[0]].mark_completed()
        
        # Get status
        status = await resilient_processor.get_queue_status()
        
        assert status["total_tasks"] == 2
        assert status["completed_tasks"] == 1
        assert status["pending_tasks"] == 1
        assert status["queue_size"] == 1
    
    @pytest.mark.asyncio
    async def test_processor_start_stop(self, resilient_processor):
        """Test starting and stopping the processor."""
        assert resilient_processor._processing == False
        
        # Start processor
        await resilient_processor.start_processor()
        assert resilient_processor._processing == True
        assert resilient_processor._processor_task is not None
        
        # Stop processor
        await resilient_processor.stop_processor()
        assert resilient_processor._processing == False


class TestNetworkFailureSimulation:
    """Test network failure simulation scenarios."""
    
    @pytest.mark.asyncio
    async def test_simulated_network_outage(self, resilient_processor):
        """Simulate network outage during processing."""
        # Mock services to simulate network failures
        resilient_processor.s3_service = AsyncMock()
        resilient_processor.openai_service = AsyncMock()
        
        # S3 fails with network error
        resilient_processor.s3_service.upload_audio.side_effect = AudioUploadError("Connection timeout")
        
        # OpenAI fails with network error
        resilient_processor.openai_service.transcribe_audio.side_effect = TranscriptionError("Rate limit exceeded")
        
        # Mock update methods
        resilient_processor._update_log_entry = AsyncMock()
        resilient_processor._mark_log_entry_failed = AsyncMock()
        
        # Create test file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(b"fake audio data")
            test_file = Path(tmp_file.name)
        
        try:
            # Queue tasks
            upload_task_id = await resilient_processor.queue_s3_upload("log_1", test_file)
            transcription_task_id = await resilient_processor.queue_transcription("log_1", audio_file=test_file)
            
            # Process tasks - they should fail but not crash the processor
            upload_task = resilient_processor.task_queue[upload_task_id]
            transcription_task = resilient_processor.task_queue[transcription_task_id]
            
            # Simulate processing attempts
            await resilient_processor._process_single_task(upload_task)
            await resilient_processor._process_single_task(transcription_task)
            
            # Verify tasks marked for retry
            assert upload_task.retry_count == 1
            assert transcription_task.retry_count == 1
            assert upload_task.should_retry() == True
            assert transcription_task.should_retry() == True
            
            # Verify error messages captured
            assert "Connection timeout" in upload_task.error_message
            assert "Rate limit exceeded" in transcription_task.error_message
        
        finally:
            # Clean up test file
            test_file.unlink()


if __name__ == "__main__":
    # Run a simple demonstration
    async def demo():
        print("Network Resilience Demo")
        print("=======================")
        
        # Create mock settings
        settings = Settings(
            openai_api_key="demo_key",
            aws_access_key_id="demo_key",
            aws_secret_access_key="demo_secret",
            s3_bucket_name="demo-bucket"
        )
        
        # Create processor
        processor = NetworkResilientProcessor(settings, None)
        
        # Queue some tasks
        task1 = await processor.queue_s3_upload("log_1", Path("/tmp/test1.wav"))
        task2 = await processor.queue_transcription("log_2", audio_file=Path("/tmp/test2.wav"))
        
        # Check status
        status = await processor.get_queue_status()
        print(f"Queue status: {status}")
        
        # Simulate completing a task
        processor.task_queue[task1].mark_completed()
        
        # Check status again
        status = await processor.get_queue_status()
        print(f"Updated status: {status}")
        
        print("Demo completed - resilient processing ready for network outages!")
    
    asyncio.run(demo())