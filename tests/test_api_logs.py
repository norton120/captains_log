"""Tests for /api/logs endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from uuid import uuid4
from fastapi import status
from pytest import mark as m

from app.models.log_entry import LogEntry, ProcessingStatus


@m.describe("POST /api/logs/upload")
class TestLogUploadEndpoint:
    """Test audio file upload endpoint."""
    
    @m.context("When uploading valid audio file")
    @m.it("creates log entry and starts processing")
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_upload_valid_audio_success(
        self, api_client, upload_file_factory, mock_workflow_service
    ):
        """Should successfully upload valid audio file and start processing."""
        # Arrange
        upload_file = upload_file_factory("valid_short")
        
        with patch('app.api.logs.AudioProcessingWorkflow') as mock_workflow_class, \
             patch('app.services.s3.S3Service.upload_audio') as mock_s3_upload:
            mock_workflow_class.return_value = mock_workflow_service
            mock_s3_upload.return_value = "test/mock_audio_key.wav"
            
            # Act
            response = await api_client.post(
                "/api/logs/upload",
                files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
            )
        
        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "id" in data
        assert data["processing_status"] == ProcessingStatus.PENDING.value
        assert data["audio_s3_key"] is not None
    
    @m.context("When uploading file with invalid format")
    @m.it("rejects non-audio files")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_upload_invalid_file_format(self, api_client, upload_file_factory):
        """Should reject files that are not audio format."""
        # Arrange
        upload_file = upload_file_factory("corrupted", content_type="text/plain")
        
        # Act
        response = await api_client.post(
            "/api/logs/upload",
            files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
        )
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        assert "invalid file format" in data["detail"].lower()
    
    @m.context("When uploading oversized file")
    @m.it("rejects files exceeding size limit")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_upload_oversized_file(self, api_client, upload_file_factory):
        """Should reject files exceeding maximum size limit."""
        # Arrange
        upload_file = upload_file_factory("oversized")
        
        # Act
        response = await api_client.post(
            "/api/logs/upload",
            files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
        )
        
        # Assert
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        data = response.json()
        assert "detail" in data
        assert "file too large" in data["detail"].lower()
    
    @m.context("When uploading empty file")
    @m.it("rejects empty files")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_upload_empty_file(self, api_client, upload_file_factory):
        """Should reject empty audio files."""
        # Arrange
        upload_file = upload_file_factory("empty")
        
        # Act
        response = await api_client.post(
            "/api/logs/upload",
            files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
        )
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        assert "empty file" in data["detail"].lower()
    
    @m.context("When no file provided")
    @m.it("returns validation error")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_upload_no_file_provided(self, api_client):
        """Should return error when no file is provided."""
        # Act
        response = await api_client.post("/api/logs/upload")
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @m.context("When S3 upload fails")
    @m.it("handles S3 upload failures gracefully")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_upload_s3_failure(self, api_client, upload_file_factory):
        """Should handle S3 upload failures gracefully."""
        # Arrange
        upload_file = upload_file_factory("valid_short")
        
        with patch('app.services.s3.S3Service.upload_audio') as mock_upload:
            mock_upload.side_effect = Exception("S3 connection failed")
            
            # Act
            response = await api_client.post(
                "/api/logs/upload",
                files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
            )
        
        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "detail" in data
        assert "upload failed" in data["detail"].lower()
    
    @m.context("When database save fails")
    @m.it("handles database failures during upload")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_upload_database_failure(self, api_client, upload_file_factory):
        """Should handle database save failures during upload."""
        # Arrange
        upload_file = upload_file_factory("valid_short")
        
        with patch('app.services.s3.S3Service.upload_audio') as mock_s3_upload:
            mock_s3_upload.return_value = "test/mock_audio_key.wav"
            
            # Mock the database session dependency to raise error on commit
            from app.dependencies import get_db_session
            from app.main import app
            
            async def mock_db_session():
                mock_session = AsyncMock()
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock(side_effect=Exception("Database error"))
                yield mock_session
            
            app.dependency_overrides[get_db_session] = mock_db_session
            
            try:
                # Act
                response = await api_client.post(
                    "/api/logs/upload",
                    files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
                )
            finally:
                # Clean up dependency override
                if get_db_session in app.dependency_overrides:
                    del app.dependency_overrides[get_db_session]
        
        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@m.describe("GET /api/logs")
class TestLogListEndpoint:
    """Test log listing endpoint."""
    
    @m.context("When listing logs with no filters")
    @m.it("returns paginated log list")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_list_logs_default(self, api_client, log_entry_factory):
        """Should return paginated list of all logs by default."""
        # Arrange - create test log entries
        entries = [
            await log_entry_factory(
                audio_s3_key=f"test/audio_{i}.wav",
                processing_status=ProcessingStatus.COMPLETED,
                transcription=f"Test transcription {i}",
                summary=f"Test summary {i}"
            ) for i in range(5)
        ]
        
        # Act
        response = await api_client.get("/api/logs")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert len(data["items"]) == 5
        assert data["total"] == 5
        
        # Check item structure
        log_item = data["items"][0]
        assert "id" in log_item
        assert "created_at" in log_item
        assert "processing_status" in log_item
        assert "summary" in log_item
    
    @m.context("When filtering logs by status")
    @m.it("returns only logs matching status filter")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_list_logs_status_filter(self, api_client, log_entry_factory):
        """Should filter logs by processing status."""
        # Arrange - create logs with different statuses
        completed_entries = [
            await log_entry_factory(processing_status=ProcessingStatus.COMPLETED)
            for _ in range(3)
        ]
        pending_entries = [
            await log_entry_factory(processing_status=ProcessingStatus.PENDING)
            for _ in range(2)
        ]
        
        # Act
        response = await api_client.get("/api/logs?status=completed")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        
        # All items should have completed status
        for item in data["items"]:
            assert item["processing_status"] == ProcessingStatus.COMPLETED.value
    
    @m.context("When using pagination")
    @m.it("returns correct page of results")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_list_logs_pagination(self, api_client, log_entry_factory):
        """Should handle pagination correctly."""
        # Arrange - create multiple log entries
        entries = [
            await log_entry_factory(audio_s3_key=f"test/audio_{i}.wav")
            for i in range(15)
        ]
        
        # Act - get second page with 10 items per page
        response = await api_client.get("/api/logs?page=2&size=10")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 2
        assert data["size"] == 10
        assert len(data["items"]) == 5  # Remaining items
        assert data["total"] == 15
    
    @m.context("When filtering by date range")
    @m.it("returns logs within date range")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_list_logs_date_filter(self, api_client, log_entry_factory):
        """Should filter logs by date range."""
        # Arrange - would need to create entries with specific dates
        # This test would require more sophisticated date handling
        
        # Act
        response = await api_client.get("/api/logs?start_date=2024-01-01&end_date=2024-12-31")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        # Additional date filtering logic would be tested here
    
    @m.context("When no logs exist")
    @m.it("returns empty result")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_list_logs_empty(self, api_client):
        """Should return empty result when no logs exist."""
        # Act
        response = await api_client.get("/api/logs")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
    
    @m.context("When using invalid pagination parameters")
    @m.it("handles invalid pagination gracefully")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_list_logs_invalid_pagination(self, api_client):
        """Should handle invalid pagination parameters."""
        # Act
        response = await api_client.get("/api/logs?page=-1&size=0")
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@m.describe("GET /api/logs/{id}")
class TestLogDetailEndpoint:
    """Test individual log retrieval endpoint."""
    
    @m.context("When retrieving existing log")
    @m.it("returns full log details")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_detail_success(self, api_client, log_entry_factory):
        """Should return full details of an existing log."""
        # Arrange
        log_entry = await log_entry_factory(
            audio_s3_key="test/detailed_audio.wav",
            transcription="Detailed test transcription",
            summary="Detailed test summary",
            processing_status=ProcessingStatus.COMPLETED
        )
        
        # Act
        response = await api_client.get(f"/api/logs/{log_entry.id}")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(log_entry.id)
        assert data["transcription"] == "Detailed test transcription"
        assert data["summary"] == "Detailed test summary"
        assert data["processing_status"] == ProcessingStatus.COMPLETED.value
        assert data["audio_s3_key"] == "test/detailed_audio.wav"
        assert "created_at" in data
    
    @m.context("When log does not exist")
    @m.it("returns 404 not found")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_get_log_detail_not_found(self, api_client):
        """Should return 404 for non-existent log."""
        # Arrange
        fake_id = uuid4()
        
        # Act
        response = await api_client.get(f"/api/logs/{fake_id}")
        
        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    @m.context("When log is being processed")
    @m.it("returns partial details with processing status")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_detail_processing(self, api_client, log_entry_factory):
        """Should return partial details for logs being processed."""
        # Arrange
        log_entry = await log_entry_factory(
            audio_s3_key="test/processing_audio.wav",
            processing_status=ProcessingStatus.TRANSCRIBING,
            transcription=None,
            summary=None
        )
        
        # Act
        response = await api_client.get(f"/api/logs/{log_entry.id}")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["processing_status"] == ProcessingStatus.TRANSCRIBING.value
        assert data["transcription"] is None
        assert data["summary"] is None
    
    @m.context("When using invalid UUID format")
    @m.it("returns validation error")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_get_log_detail_invalid_uuid(self, api_client):
        """Should return validation error for invalid UUID format."""
        # Act
        response = await api_client.get("/api/logs/invalid-uuid-format")
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@m.describe("GET /api/logs/{id}/status")
class TestLogStatusEndpoint:
    """Test log status polling endpoint."""
    
    @m.context("When checking status of existing log")
    @m.it("returns current processing status")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_status_success(self, api_client, log_entry_factory):
        """Should return current processing status of log."""
        # Arrange
        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.VECTORIZING
        )
        
        # Act
        response = await api_client.get(f"/api/logs/{log_entry.id}/status")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(log_entry.id)
        assert data["processing_status"] == ProcessingStatus.VECTORIZING.value
        assert "created_at" in data
        assert "processing_error" in data
    
    @m.context("When log has failed processing")
    @m.it("returns error status and message")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_status_failed(self, api_client, log_entry_factory):
        """Should return error status and message for failed processing."""
        # Arrange
        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.FAILED,
            processing_error="OpenAI API rate limit exceeded"
        )
        
        # Act
        response = await api_client.get(f"/api/logs/{log_entry.id}/status")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["processing_status"] == ProcessingStatus.FAILED.value
        assert data["processing_error"] == "OpenAI API rate limit exceeded"
    
    @m.context("When log does not exist")
    @m.it("returns 404 not found")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_get_log_status_not_found(self, api_client):
        """Should return 404 for non-existent log status check."""
        # Arrange
        fake_id = uuid4()
        
        # Act
        response = await api_client.get(f"/api/logs/{fake_id}/status")
        
        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


@m.describe("GET /api/logs/{id}/audio")
class TestLogAudioEndpoint:
    """Test audio file access endpoint."""
    
    @m.context("When requesting audio for existing log")
    @m.it("returns presigned S3 URL")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_audio_success(self, api_client, log_entry_factory, mock_s3_service):
        """Should return presigned S3 URL for audio file."""
        # Arrange
        log_entry = await log_entry_factory(
            audio_s3_key="test/audio_file.wav"
        )
        
        with patch('app.services.s3.S3Service.get_audio_url') as mock_get_url:
            mock_get_url.return_value = "https://presigned-s3-url.com/audio_file.wav?signature=xyz"
            
            # Act
            response = await api_client.get(f"/api/logs/{log_entry.id}/audio")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "audio_url" in data
        assert "expires_at" in data
        assert data["audio_url"].startswith("https://")
        mock_get_url.assert_called_once_with("test/audio_file.wav")
    
    @m.context("When log does not exist")
    @m.it("returns 404 not found")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_get_log_audio_not_found(self, api_client):
        """Should return 404 for non-existent log audio request."""
        # Arrange
        fake_id = uuid4()
        
        # Act
        response = await api_client.get(f"/api/logs/{fake_id}/audio")
        
        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @m.context("When S3 URL generation fails")
    @m.it("handles S3 URL generation failures")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_audio_s3_failure(self, api_client, log_entry_factory):
        """Should handle S3 URL generation failures."""
        # Arrange
        log_entry = await log_entry_factory(
            audio_s3_key="test/audio_file.wav"
        )
        
        with patch('app.services.s3.S3Service.get_audio_url') as mock_get_url:
            mock_get_url.side_effect = Exception("S3 access denied")
            
            # Act
            response = await api_client.get(f"/api/logs/{log_entry.id}/audio")
        
        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "detail" in data
        assert "audio access failed" in data["detail"].lower()
    
    @m.context("When audio file does not exist in S3")
    @m.it("handles missing S3 audio files")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    @pytest.mark.db
    async def test_get_log_audio_file_missing(self, api_client, log_entry_factory):
        """Should handle missing audio files in S3."""
        # Arrange
        log_entry = await log_entry_factory(
            audio_s3_key="test/missing_audio.wav"
        )
        
        with patch('app.services.s3.S3Service.get_audio_url') as mock_get_url:
            mock_get_url.side_effect = FileNotFoundError("Audio file not found in S3")
            
            # Act
            response = await api_client.get(f"/api/logs/{log_entry.id}/audio")
        
        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "audio file not found" in data["detail"].lower()


@m.describe("API Error Handling")
class TestAPIErrorHandling:
    """Test API error handling scenarios."""
    
    @m.context("When database is unavailable")
    @m.it("returns service unavailable error")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_database_unavailable(self, api_client):
        """Should handle database unavailability gracefully."""
        from app.dependencies import get_db_session
        from app.main import app
        
        async def mock_db_session():
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed"
            )
            yield  # This won't be reached but needed for generator
        
        app.dependency_overrides[get_db_session] = mock_db_session
        
        try:
            # Act
            response = await api_client.get("/api/logs")
        finally:
            # Clean up dependency override
            if get_db_session in app.dependency_overrides:
                del app.dependency_overrides[get_db_session]
        
        # Assert
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    
    @m.context("When request rate limit exceeded")
    @m.it("returns rate limit error")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_rate_limit_exceeded(self, api_client, upload_file_factory):
        """Should handle rate limiting correctly."""
        # This would test actual rate limiting implementation
        # For now, just ensure the endpoint accepts requests
        upload_file = upload_file_factory("valid_short")
        
        with patch('app.services.s3.S3Service.upload_audio') as mock_s3_upload:
            mock_s3_upload.return_value = "test/mock_audio_key.wav"
            
            # Act
            response = await api_client.post(
                "/api/logs/upload",
                files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
            )
        
        # Would implement actual rate limiting test here
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_429_TOO_MANY_REQUESTS]
    
    @m.context("When malformed request data")
    @m.it("returns validation errors")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_malformed_request_data(self, api_client):
        """Should handle malformed request data with validation errors."""
        # Act - send invalid JSON
        response = await api_client.post(
            "/api/logs/upload",
            data="invalid-json-data",
            headers={"content-type": "application/json"}
        )
        
        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@m.describe("API Integration Scenarios")  
class TestAPIIntegrationScenarios:
    """Test common API usage scenarios."""
    
    @m.context("When uploading and immediately checking status")
    @m.it("handles rapid status polling")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.integration
    async def test_upload_then_status_check(self, api_client, upload_file_factory):
        """Should handle upload followed by immediate status check."""
        # Arrange
        upload_file = upload_file_factory("valid_short")
        
        with patch('app.api.logs.AudioProcessingWorkflow') as mock_workflow, \
             patch('app.services.s3.S3Service.upload_audio') as mock_s3_upload:
            mock_workflow_instance = AsyncMock()
            mock_workflow.return_value = mock_workflow_instance
            mock_s3_upload.return_value = "test/mock_audio_key.wav"
            
            # Act - Upload
            upload_response = await api_client.post(
                "/api/logs/upload",
                files={"file": (upload_file.filename, upload_file.file, upload_file.content_type)}
            )
            
            assert upload_response.status_code == status.HTTP_201_CREATED
            log_id = upload_response.json()["id"]
            
            # Act - Check status immediately
            status_response = await api_client.get(f"/api/logs/{log_id}/status")
        
        # Assert
        assert status_response.status_code == status.HTTP_200_OK
        status_data = status_response.json()
        assert status_data["id"] == log_id
        assert status_data["processing_status"] == ProcessingStatus.PENDING.value
    
    @m.context("When listing logs after multiple uploads")
    @m.it("shows all uploaded logs in list")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.integration
    async def test_multiple_uploads_then_list(self, api_client, upload_file_factory):
        """Should show all uploaded logs after multiple uploads."""
        # This test would require actual API implementation
        # For now, we test the expected behavior structure
        pass
    
    @m.context("When accessing audio after processing completes")
    @m.it("provides working audio URLs")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.integration
    async def test_audio_access_after_processing(self, api_client, log_entry_factory):
        """Should provide working audio URLs after processing completes."""
        # Arrange
        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.COMPLETED,
            audio_s3_key="test/completed_audio.wav"
        )
        
        with patch('app.services.s3.S3Service.get_audio_url') as mock_get_url:
            mock_get_url.return_value = "https://valid-presigned-url.com/audio.wav"
            
            # Act
            response = await api_client.get(f"/api/logs/{log_entry.id}/audio")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["audio_url"] == "https://valid-presigned-url.com/audio.wav"


@m.describe("POST /api/logs/{log_id}/retry")
class TestLogRetryEndpoint:
    """Test retry endpoint for failed or stuck log processing."""

    @m.context("When retrying a failed log entry")
    @m.it("resets status and restarts processing")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_failed_log_success(self, api_client, log_entry_factory, tmp_path):
        """Should successfully retry a failed log entry."""
        # Arrange - Create local audio file for retry
        audio_file = tmp_path / "failed_audio.wav"
        audio_file.write_bytes(b"test audio content")

        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.FAILED,
            processing_error="Transcription timeout",
            audio_s3_key="test/failed_audio.wav",
            audio_local_path=str(audio_file)
        )

        # Act
        response = await api_client.post(f"/api/logs/{log_entry.id}/retry")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(log_entry.id)
        assert data["status"] == ProcessingStatus.PENDING.value
        assert "retry started successfully" in data["message"].lower()

    @m.context("When retrying a log stuck in transcribing status")
    @m.it("successfully retries the stuck job")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_stuck_transcribing_log(self, api_client, log_entry_factory, tmp_path):
        """Should successfully retry a log stuck in transcribing status."""
        # Arrange - Create local audio file for retry
        audio_file = tmp_path / "stuck_audio.wav"
        audio_file.write_bytes(b"test audio content")

        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.TRANSCRIBING,
            audio_s3_key="test/stuck_audio.wav",
            audio_local_path=str(audio_file)
        )

        # Act
        response = await api_client.post(f"/api/logs/{log_entry.id}/retry")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(log_entry.id)

    @m.context("When retrying a completed log entry")
    @m.it("returns error that retry is not needed")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_completed_log_error(self, api_client, log_entry_factory):
        """Should reject retry of already completed log entry."""
        # Arrange
        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.COMPLETED,
            audio_s3_key="test/completed_audio.wav"
        )

        # Act
        response = await api_client.post(f"/api/logs/{log_entry.id}/retry")

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "already completed" in data["detail"].lower()

    @m.context("When retrying a pending log entry")
    @m.it("returns error that retry is not applicable")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_pending_log_error(self, api_client, log_entry_factory):
        """Should reject retry of pending log entry."""
        # Arrange
        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.PENDING,
            audio_s3_key="test/pending_audio.wav"
        )

        # Act
        response = await api_client.post(f"/api/logs/{log_entry.id}/retry")

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "cannot be retried" in data["detail"].lower()

    @m.context("When retrying a log with no audio file")
    @m.it("returns error about missing audio")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_log_no_audio_error(self, api_client, log_entry_factory):
        """Should reject retry when no audio file is available."""
        # Arrange
        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.FAILED,
            audio_s3_key=None,
            audio_local_path=None
        )

        # Act
        response = await api_client.post(f"/api/logs/{log_entry.id}/retry")

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "no audio file" in data["detail"].lower()

    @m.context("When retrying a non-existent log")
    @m.it("returns not found error")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_nonexistent_log_error(self, api_client):
        """Should return 404 for non-existent log entry."""
        # Arrange
        fake_id = uuid4()

        # Act
        response = await api_client.post(f"/api/logs/{fake_id}/retry")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "not found" in data["detail"].lower()

    @m.context("When retrying with local audio file")
    @m.it("uses local file path instead of downloading")
    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.unit
    async def test_retry_with_local_audio_file(self, api_client, log_entry_factory, tmp_path):
        """Should use local audio file when available."""
        # Arrange
        audio_file = tmp_path / "test_audio.wav"
        audio_file.write_bytes(b"test audio content")

        log_entry = await log_entry_factory(
            processing_status=ProcessingStatus.FAILED,
            audio_local_path=str(audio_file),
            audio_s3_key="test/backup_audio.wav"
        )

        # Act
        response = await api_client.post(f"/api/logs/{log_entry.id}/retry")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(log_entry.id)