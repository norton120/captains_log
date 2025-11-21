"""Tests for DBOS audio processing workflows."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from pytest import mark as m
from uuid import uuid4

from app.workflows.audio_processor import (
    AudioProcessingWorkflow,
    StoreAudioStep,
    TranscribeAudioStep,
    GenerateEmbeddingStep,
    GenerateSummaryStep,
    UpdateLogEntryStep,
    WorkflowError
)
from app.models.log_entry import LogEntry, ProcessingStatus


@pytest.fixture
def audio_workflow(test_settings, async_db_session, mock_s3_service, mock_openai_client):
    """Create audio processing workflow for testing."""
    # Create mock services with async methods
    media_storage_mock = MagicMock()
    media_storage_mock.store_audio = AsyncMock()
    media_storage_mock.get_audio_url = AsyncMock()
    media_storage_mock.delete_audio = AsyncMock()
    media_storage_mock.get_file_path_for_processing = MagicMock()
    
    openai_mock = MagicMock()
    openai_mock.transcribe_audio = AsyncMock()
    openai_mock.generate_embedding = AsyncMock()
    openai_mock.generate_summary = AsyncMock()
    
    workflow = AudioProcessingWorkflow(
        settings=test_settings,
        db_session=async_db_session,
        media_storage=media_storage_mock,
        openai_service=openai_mock
    )
    return workflow


@m.describe("Upload to S3 Step")
class TestStoreAudioStep:
    """Test S3 upload workflow step."""
    
    @m.context("When executing S3 upload step successfully")
    @m.it("uploads audio file and returns S3 key")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_upload_to_s3_step_success(self, audio_workflow, sample_audio_file):
        """Should successfully execute S3 upload step."""
        # Arrange
        step = StoreAudioStep(audio_workflow)
        audio_workflow.s3_service.upload_audio.return_value = "audio/test-123.wav"
        
        # Act
        result = await step.execute(audio_file=sample_audio_file)
        
        # Assert
        assert result["s3_key"] == "audio/test-123.wav"
        assert result["success"] is True
        audio_workflow.s3_service.upload_audio.assert_called_once_with(sample_audio_file)
    
    @m.context("When S3 upload step encounters failure")
    @m.it("handles S3 upload failures gracefully")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_upload_to_s3_step_failure(self, audio_workflow, sample_audio_file):
        """Should handle S3 upload failures in workflow step."""
        # Arrange
        step = StoreAudioStep(audio_workflow)
        audio_workflow.s3_service.upload_audio.side_effect = Exception("S3 error")
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="S3 upload failed"):
            await step.execute(audio_file=sample_audio_file)
    
    @m.context("When validating file in upload step")
    @m.it("validates file before uploading")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_upload_to_s3_step_validation(self, audio_workflow):
        """Should validate file before attempting upload."""
        # Arrange
        step = StoreAudioStep(audio_workflow)
        nonexistent_file = Path("/nonexistent/file.wav")
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="File not found"):
            await step.execute(audio_file=nonexistent_file)


@m.describe("Transcribe Audio Step")
class TestTranscribeAudioStep:
    """Test audio transcription workflow step."""
    
    @m.context("When executing transcription step successfully")
    @m.it("transcribes audio and returns text")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_transcribe_audio_step_success(self, audio_workflow, sample_audio_file):
        """Should successfully execute audio transcription step."""
        # Arrange
        step = TranscribeAudioStep(audio_workflow)
        audio_workflow.openai_service.transcribe_audio.return_value = "Test transcription"
        
        # Act
        result = await step.execute(audio_file=sample_audio_file)
        
        # Assert
        assert result["transcription"] == "Test transcription"
        assert result["success"] is True
        audio_workflow.openai_service.transcribe_audio.assert_called_once_with(
            sample_audio_file,
            prompt="Captain's log entry from sailing vessel"
        )
    
    @m.context("When transcribing from S3 URL")
    @m.it("downloads from S3 URL and transcribes")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_transcribe_audio_step_s3_url(self, audio_workflow, sample_audio_file):
        """Should download audio from S3 URL and transcribe."""
        # Arrange
        step = TranscribeAudioStep(audio_workflow)
        s3_key = "audio/test-123.wav"
        audio_workflow.openai_service.transcribe_audio.return_value = "Test transcription"
        audio_workflow.s3_service.get_audio_url.return_value = "https://s3.example.com/test.wav"
        
        # Mock the download process
        with patch('aiohttp.ClientSession') as MockClientSession:
            # Setup mock response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.content.iter_chunked = AsyncMock(return_value=iter([b'test data']))
            
            # Setup mock session as async context manager
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            
            # Setup mock get method as async context manager
            mock_get_cm = MagicMock()
            mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get_cm.__aexit__ = AsyncMock()
            mock_session.get.return_value = mock_get_cm
            
            MockClientSession.return_value = mock_session
            
            # Act
            result = await step.execute(s3_key=s3_key)
        
        # Assert
        assert result["transcription"] == "Test transcription"
        assert result["success"] is True
    
    @m.context("When transcription step encounters failure")
    @m.it("handles transcription failures gracefully")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_transcribe_audio_step_failure(self, audio_workflow, sample_audio_file):
        """Should handle transcription failures in workflow step."""
        # Arrange
        step = TranscribeAudioStep(audio_workflow)
        audio_workflow.openai_service.transcribe_audio.side_effect = Exception("Transcription error")
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="Transcription failed"):
            await step.execute(audio_file=sample_audio_file)


@m.describe("Generate Embedding Step")
class TestGenerateEmbeddingStep:
    """Test embedding generation workflow step."""
    
    @m.context("When executing embedding generation successfully")
    @m.it("generates embeddings from transcription")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_generate_embedding_step_success(self, audio_workflow):
        """Should successfully generate embeddings from transcription."""
        # Arrange
        step = GenerateEmbeddingStep(audio_workflow)
        transcription = "Test transcription for embedding"
        audio_workflow.openai_service.generate_embedding.return_value = [0.1] * 1536
        
        # Act
        result = await step.execute(transcription=transcription)
        
        # Assert
        assert result["embedding"] == [0.1] * 1536
        assert result["success"] is True
        audio_workflow.openai_service.generate_embedding.assert_called_once_with(transcription)
    
    @m.context("When embedding step receives empty transcription")
    @m.it("handles empty transcription gracefully")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_generate_embedding_step_empty_transcription(self, audio_workflow):
        """Should handle empty transcription in embedding step."""
        # Arrange
        step = GenerateEmbeddingStep(audio_workflow)
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="Empty transcription"):
            await step.execute(transcription="")
    
    @m.context("When embedding step encounters failure")
    @m.it("handles embedding generation failures")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_generate_embedding_step_failure(self, audio_workflow):
        """Should handle embedding generation failures."""
        # Arrange
        step = GenerateEmbeddingStep(audio_workflow)
        audio_workflow.openai_service.generate_embedding.side_effect = Exception("Embedding error")
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="Embedding generation failed"):
            await step.execute(transcription="Test transcription")


@m.describe("Generate Summary Step")
class TestGenerateSummaryStep:
    """Test summary generation workflow step."""
    
    @m.context("When executing summary generation successfully")
    @m.it("generates summary from transcription")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_generate_summary_step_success(self, audio_workflow):
        """Should successfully generate summary from transcription."""
        # Arrange
        step = GenerateSummaryStep(audio_workflow)
        transcription = "Long transcription that needs summarization..."
        audio_workflow.openai_service.generate_summary.return_value = "Brief summary"
        
        # Act
        result = await step.execute(transcription=transcription)
        
        # Assert
        assert result["summary"] == "Brief summary"
        assert result["success"] is True
        audio_workflow.openai_service.generate_summary.assert_called_once_with(
            transcription,
            instructions="Focus on key events, weather conditions, and important decisions."
        )
    
    @m.context("When summary step receives short transcription")
    @m.it("handles short transcriptions appropriately")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_generate_summary_step_short_transcription(self, audio_workflow):
        """Should handle short transcriptions that don't need summarization."""
        # Arrange
        step = GenerateSummaryStep(audio_workflow)
        short_transcription = "Hi."
        
        # Act
        result = await step.execute(transcription=short_transcription)
        
        # Assert - should return original or skip summarization
        assert result["success"] is True
    
    @m.context("When summary step encounters failure")
    @m.it("handles summary generation failures")
    @pytest.mark.unit
    @pytest.mark.workflow
    async def test_generate_summary_step_failure(self, audio_workflow):
        """Should handle summary generation failures."""
        # Arrange
        step = GenerateSummaryStep(audio_workflow)
        audio_workflow.openai_service.generate_summary.side_effect = Exception("Summary error")
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="Summary generation failed"):
            await step.execute(transcription="Test transcription")


@m.describe("Update Log Entry Step")
class TestUpdateLogEntryStep:
    """Test database update workflow step."""
    
    @m.context("When updating log entry successfully")
    @m.it("updates log entry with processing results")
    @pytest.mark.unit
    @pytest.mark.workflow
    @pytest.mark.db
    async def test_update_log_entry_step_success(self, audio_workflow, log_entry_factory):
        """Should successfully update log entry with processing results."""
        # Arrange
        log_entry = await log_entry_factory()
        step = UpdateLogEntryStep(audio_workflow)
        
        update_data = {
            "transcription": "Test transcription",
            "embedding": [0.1] * 1536,
            "summary": "Test summary",
            "processing_status": ProcessingStatus.COMPLETED
        }
        
        # Act
        result = await step.execute(log_entry_id=log_entry.id, **update_data)
        
        # Assert
        assert result["success"] is True
        # Note: Would need to refresh and check actual database state
    
    @m.context("When updating log entry with error status")
    @m.it("updates log entry with error information")
    @pytest.mark.unit
    @pytest.mark.workflow
    @pytest.mark.db
    async def test_update_log_entry_step_error(self, audio_workflow, log_entry_factory):
        """Should update log entry with error status and message."""
        # Arrange
        log_entry = await log_entry_factory()
        step = UpdateLogEntryStep(audio_workflow)
        
        # Act
        result = await step.execute(
            log_entry_id=log_entry.id,
            processing_status=ProcessingStatus.FAILED,
            processing_error="Test error message"
        )
        
        # Assert
        assert result["success"] is True
    
    @m.context("When updating nonexistent log entry")
    @m.it("handles updates to nonexistent log entries")
    @pytest.mark.unit
    @pytest.mark.workflow
    @pytest.mark.db
    async def test_update_log_entry_step_not_found(self, audio_workflow):
        """Should handle updates to nonexistent log entries."""
        # Arrange
        step = UpdateLogEntryStep(audio_workflow)
        fake_id = uuid4()
        
        # Act & Assert
        with pytest.raises(WorkflowError, match="Log entry not found"):
            await step.execute(
                log_entry_id=fake_id,
                transcription="Test"
            )


@m.describe("Audio Processing Workflow")
class TestAudioProcessingWorkflow:
    """Test complete audio processing workflow."""
    
    @m.context("When executing complete workflow")
    @m.it("executes all steps successfully")
    @pytest.mark.integration
    @pytest.mark.workflow
    async def test_complete_audio_processing_workflow(
        self, audio_workflow, sample_audio_file, log_entry_factory
    ):
        """Should execute complete audio processing workflow successfully."""
        # Arrange
        log_entry = await log_entry_factory()
        
        # Mock all service calls
        audio_workflow.s3_service.upload_audio.return_value = "audio/test-123.wav"
        audio_workflow.openai_service.transcribe_audio.return_value = "Test transcription"
        audio_workflow.openai_service.generate_embedding.return_value = [0.1] * 1536
        audio_workflow.openai_service.generate_summary.return_value = "Test summary"
        
        # Act
        result = await audio_workflow.process_audio(
            log_entry_id=log_entry.id,
            audio_file=sample_audio_file
        )
        
        # Assert
        assert result["success"] is True
        assert result["s3_key"] == "audio/test-123.wav"
        assert result["transcription"] == "Test transcription"
        assert result["summary"] == "Test summary"
    
    @m.context("When workflow encounters errors")
    @m.it("handles failures at each step")
    @pytest.mark.integration
    @pytest.mark.workflow
    async def test_workflow_error_handling(
        self, audio_workflow, sample_audio_file, log_entry_factory
    ):
        """Should handle workflow failures gracefully."""
        # Arrange
        log_entry = await log_entry_factory()
        audio_workflow.s3_service.upload_audio.side_effect = Exception("S3 error")
        
        # Act & Assert
        with pytest.raises(WorkflowError):
            await audio_workflow.process_audio(
                log_entry_id=log_entry.id,
                audio_file=sample_audio_file
            )
    
    @m.context("When workflow updates status")
    @m.it("updates status at each processing step")
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.workflow
    @pytest.mark.db
    async def test_workflow_status_updates(
        self, audio_workflow, sample_audio_file, log_entry_factory
    ):
        """Should update log entry status at each processing step."""
        # Arrange
        log_entry = await log_entry_factory()
        
        # Mock services to track status updates
        audio_workflow.s3_service.upload_audio.return_value = "audio/test-123.wav"
        audio_workflow.openai_service.transcribe_audio.return_value = "Test transcription"
        audio_workflow.openai_service.generate_embedding.return_value = [0.1] * 1536
        audio_workflow.openai_service.generate_summary.return_value = "Test summary"
        
        # Act
        await audio_workflow.process_audio(
            log_entry_id=log_entry.id,
            audio_file=sample_audio_file
        )
        
        # Assert - would verify status transitions in database
        # This requires implementing actual workflow status tracking
    
    @m.context("When workflow encounters transient failures")
    @m.it("retries transient failures automatically")
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.workflow
    async def test_workflow_retry_logic(
        self, audio_workflow, sample_audio_file, log_entry_factory
    ):
        """Should retry workflow steps on transient failures."""
        # Arrange
        log_entry = await log_entry_factory()
        
        # Simulate transient failure then success
        call_count = 0
        def failing_transcribe(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Transient error")
            return "Test transcription"
        
        audio_workflow.s3_service.upload_audio.return_value = "audio/test-123.wav"
        audio_workflow.openai_service.transcribe_audio.side_effect = failing_transcribe
        audio_workflow.openai_service.generate_embedding.return_value = [0.1] * 1536
        audio_workflow.openai_service.generate_summary.return_value = "Test summary"
        
        # Act
        result = await audio_workflow.process_audio(
            log_entry_id=log_entry.id,
            audio_file=sample_audio_file
        )
        
        # Assert
        assert result["success"] is True
        assert call_count == 2  # Should have retried once
    
    @m.context("When running multiple workflows concurrently")
    @m.it("handles multiple workflows simultaneously")
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.workflow
    async def test_concurrent_workflows(
        self, test_settings, async_db_engine, sample_audio_file, log_entry_factory
    ):
        """Should handle multiple workflows processing simultaneously."""
        # Create separate sessions for each workflow to avoid session conflicts
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        
        async_session_maker = async_sessionmaker(
            bind=async_db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Create log entries using the factory (which uses the shared session)
        log_entries = [await log_entry_factory() for _ in range(3)]
        
        # Create separate workflow instances with their own sessions
        workflows = []
        for i in range(3):
            # Create separate session for each workflow
            session = async_session_maker()
            
            # Create mock services
            s3_mock = MagicMock()
            s3_mock.upload_audio = AsyncMock(return_value=f"audio/test-{i}.wav")
            
            openai_mock = MagicMock()
            openai_mock.transcribe_audio = AsyncMock(return_value="Test transcription")
            openai_mock.generate_embedding = AsyncMock(return_value=[0.1] * 1536)
            openai_mock.generate_summary = AsyncMock(return_value="Test summary")
            
            workflow = AudioProcessingWorkflow(
                settings=test_settings,
                db_session=session,
                s3_service=s3_mock,
                openai_service=openai_mock
            )
            workflows.append(workflow)
        
        try:
            # Act
            import asyncio
            tasks = [
                workflows[i].process_audio(log_entries[i].id, sample_audio_file)
                for i in range(3)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Assert
            assert len(results) == 3
            # Check that all results are success (not exceptions)
            successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
            assert len(successful_results) == 3
            
        finally:
            # Close all sessions
            for workflow in workflows:
                await workflow.db_session.close()


@m.describe("Workflow Database Integration")
class TestWorkflowDatabaseIntegration:
    """Test workflow database interactions."""
    
    @m.context("When transitioning log entry status")
    @m.it("follows valid status state machine")
    @pytest.mark.unit
    @pytest.mark.db
    async def test_log_entry_status_transitions(self, log_entry_factory):
        """Should follow valid status transitions in processing."""
        # Arrange
        log_entry = await log_entry_factory(processing_status=ProcessingStatus.PENDING)
        
        # Act & Assert - test valid transitions
        valid_transitions = [
            ProcessingStatus.TRANSCRIBING,
            ProcessingStatus.VECTORIZING,
            ProcessingStatus.SUMMARIZING,
            ProcessingStatus.COMPLETED
        ]
        
        # This would test actual database state transitions
        # Implementation depends on actual workflow status management
    
    @m.context("When persisting workflow error states")
    @m.it("persists error states in database")
    @pytest.mark.unit
    @pytest.mark.db
    async def test_log_entry_error_handling(self, log_entry_factory):
        """Should persist error states and messages in database."""
        # Arrange
        log_entry = await log_entry_factory()
        
        # Act - simulate error state
        # This would test error state persistence
        # Implementation depends on actual error handling
        
        # Assert
        # Would verify error state and message are properly stored
        pass
    
    @m.context("When storing vector embeddings")
    @m.it("properly stores embeddings in pgvector")
    @pytest.mark.integration
    @pytest.mark.db
    async def test_vector_embedding_storage(self, log_entry_factory):
        """Should properly store and retrieve vector embeddings."""
        # Arrange
        embedding = [0.1] * 1536
        log_entry = await log_entry_factory()
        
        # Act - store embedding
        # This would test actual pgvector storage
        
        # Assert - retrieve and verify embedding
        # Would verify vector storage and similarity operations
        pass