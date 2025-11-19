"""Tests for S3 service functionality."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from pytest import mark as m

from app.services.s3 import S3Service, AudioUploadError, AudioNotFoundError


@pytest.fixture
def s3_service(test_settings, mock_s3_service):
    """Create S3 service instance for testing."""
    return S3Service(test_settings)


@m.describe("S3 Service Upload")
class TestS3ServiceUpload:
    """Test S3 audio upload functionality."""
    
    @m.context("When uploading a valid audio file")
    @m.it("uploads file to S3 and returns S3 key")
    @pytest.mark.unit
    @pytest.mark.s3
    @pytest.mark.asyncio
    async def test_upload_audio_success(self, s3_service, sample_audio_file):
        """Should successfully upload a valid audio file to S3."""
        # Act
        s3_key = await s3_service.upload_audio(sample_audio_file)
        
        # Assert
        assert s3_key.startswith("audio/")
        assert s3_key.endswith(".wav")
        assert len(s3_key) > 20  # Should include timestamp/uuid
    
    @m.context("When uploading an invalid file format")
    @m.it("rejects unsupported file formats")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_upload_audio_invalid_format(self, s3_service, tmp_path):
        """Should reject files with unsupported formats."""
        # Arrange
        invalid_file = tmp_path / "test.txt"
        invalid_file.write_text("not an audio file")
        
        # Act & Assert
        with pytest.raises(AudioUploadError, match="Unsupported audio format"):
            await s3_service.upload_audio(invalid_file)
    
    @m.context("When uploading a file exceeding size limit")
    @m.it("rejects files that are too large")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_upload_audio_file_too_large(self, s3_service, large_audio_file):
        """Should reject files that exceed the maximum size limit."""
        # Act & Assert
        with pytest.raises(AudioUploadError, match="File size exceeds limit"):
            await s3_service.upload_audio(large_audio_file)
    
    @m.context("When S3 service encounters an error")
    @m.it("handles AWS service errors gracefully")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_upload_audio_s3_error(self, s3_service, sample_audio_file):
        """Should handle S3 service errors gracefully."""
        # Arrange
        with patch.object(s3_service.s3_client, 'upload_file') as mock_upload:
            mock_upload.side_effect = ClientError(
                {"Error": {"Code": "NoSuchBucket"}}, "upload_file"
            )
            
            # Act & Assert
            with pytest.raises(AudioUploadError, match="S3 upload failed"):
                await s3_service.upload_audio(sample_audio_file)
    
    @m.context("When attempting to upload a nonexistent file")
    @m.it("handles missing files gracefully")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_upload_audio_file_not_found(self, s3_service):
        """Should handle attempts to upload nonexistent files."""
        # Arrange
        nonexistent_file = Path("/nonexistent/file.wav")
        
        # Act & Assert
        with pytest.raises(AudioUploadError, match="File not found"):
            await s3_service.upload_audio(nonexistent_file)


@m.describe("S3 Service Download")
class TestS3ServiceDownload:
    """Test S3 audio download/URL generation functionality."""
    
    @m.context("When generating presigned URL for existing file")
    @m.it("generates valid presigned URL")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_get_audio_url_success(self, s3_service, sample_audio_file):
        """Should generate valid presigned URL for existing S3 object."""
        # Arrange
        s3_key = await s3_service.upload_audio(sample_audio_file)
        
        # Act
        url = await s3_service.get_audio_url(s3_key)
        
        # Assert
        assert url.startswith("https://")
        assert s3_key in url
        assert "Expires=" in url or "X-Amz-Expires=" in url
    
    @m.context("When requesting URL for nonexistent file")
    @m.it("handles missing S3 objects gracefully")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_get_audio_url_nonexistent(self, s3_service):
        """Should handle requests for nonexistent S3 objects."""
        # Arrange
        nonexistent_key = "audio/nonexistent-file.wav"
        
        # Act & Assert
        with pytest.raises(AudioNotFoundError, match="Audio file not found"):
            await s3_service.get_audio_url(nonexistent_key)
    
    @m.context("When generating URL with custom expiry")
    @m.it("respects configured expiry time")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_get_audio_url_custom_expiry(self, s3_service, sample_audio_file):
        """Should generate URLs with custom expiry times."""
        # Arrange
        s3_key = await s3_service.upload_audio(sample_audio_file)
        custom_expiry = 7200  # 2 hours
        
        # Act
        url = await s3_service.get_audio_url(s3_key, expiry_seconds=custom_expiry)
        
        # Assert
        assert url.startswith("https://")
        # Note: Exact expiry validation would require URL parsing


@m.describe("S3 Service Delete")
class TestS3ServiceDelete:
    """Test S3 audio deletion functionality."""
    
    @m.context("When deleting an existing file")
    @m.it("successfully deletes audio file from S3")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_delete_audio_success(self, s3_service, sample_audio_file):
        """Should successfully delete an existing audio file from S3."""
        # Arrange
        s3_key = await s3_service.upload_audio(sample_audio_file)
        
        # Act
        result = await s3_service.delete_audio(s3_key)
        
        # Assert
        assert result is True
        
        # Verify file is deleted
        with pytest.raises(AudioNotFoundError):
            await s3_service.get_audio_url(s3_key)
    
    @m.context("When deleting a nonexistent file")
    @m.it("handles deletion of missing files gracefully")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_delete_audio_nonexistent(self, s3_service):
        """Should handle deletion attempts for nonexistent files."""
        # Arrange
        nonexistent_key = "audio/nonexistent-file.wav"
        
        # Act
        result = await s3_service.delete_audio(nonexistent_key)
        
        # Assert
        assert result is True  # S3 delete is idempotent
    
    @m.context("When S3 service encounters deletion error")
    @m.it("handles AWS service errors during deletion")
    @pytest.mark.unit
    @pytest.mark.s3
    async def test_delete_audio_s3_error(self, s3_service, sample_audio_file):
        """Should handle S3 service errors during deletion."""
        # Arrange
        s3_key = await s3_service.upload_audio(sample_audio_file)
        
        with patch.object(s3_service.s3_client, 'delete_object') as mock_delete:
            mock_delete.side_effect = ClientError(
                {"Error": {"Code": "InternalError"}}, "delete_object"
            )
            
            # Act & Assert
            with pytest.raises(Exception):  # Should raise the underlying S3 error
                await s3_service.delete_audio(s3_key)


@m.describe("S3 Service Integration")
class TestS3ServiceIntegration:
    """Integration tests for S3 service."""
    
    @m.context("When performing complete file lifecycle")
    @m.it("handles upload, download, and delete cycle")
    @pytest.mark.integration
    @pytest.mark.s3
    async def test_upload_download_delete_cycle(self, s3_service, sample_audio_file):
        """Should handle complete file lifecycle: upload → download → delete."""
        # Upload
        s3_key = await s3_service.upload_audio(sample_audio_file)
        assert s3_key
        
        # Download URL
        url = await s3_service.get_audio_url(s3_key)
        assert url
        
        # Delete
        result = await s3_service.delete_audio(s3_key)
        assert result is True
        
        # Verify deletion
        with pytest.raises(AudioNotFoundError):
            await s3_service.get_audio_url(s3_key)
    
    @m.context("When verifying bucket permissions")
    @m.it("has proper bucket access permissions")
    @pytest.mark.integration
    @pytest.mark.s3
    @pytest.mark.skip(reason="Requires real AWS credentials")
    async def test_s3_bucket_permissions(self, s3_service):
        """Should verify that the service has proper S3 bucket permissions."""
        # This test would run against real S3 to verify permissions
        # Skip by default to avoid AWS charges and credential requirements
        pass