"""S3 service for audio file storage and management."""
import asyncio
import os
from datetime import datetime, timedelta
import datetime as dt
from pathlib import Path
from typing import Optional
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

from app.config import Settings


class AudioUploadError(Exception):
    """Exception raised when audio upload fails."""
    pass


class AudioNotFoundError(Exception):
    """Exception raised when audio file is not found."""
    pass


class S3Service:
    """Service for managing audio files in S3."""
    
    def __init__(self, settings: Settings):
        """Initialize S3 service with configuration."""
        self.settings = settings
        self._s3_client = None
        
        # Configure boto3 client
        self.config = Config(
            region_name=settings.aws_region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )
    
    @property
    def s3_client(self):
        """Lazy-loaded S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client('s3', config=self.config)
        return self._s3_client
    
    def _generate_s3_key(self, file_path: Path, prefix: str = None) -> str:
        """Generate a unique S3 key for the media file."""
        if prefix is None:
            prefix = self.settings.s3_audio_prefix
        timestamp = datetime.now(dt.timezone.utc).strftime("%Y/%m/%d")
        unique_id = str(uuid4())[:8]
        file_extension = file_path.suffix.lower()
        
        return f"{prefix}{timestamp}/{unique_id}{file_extension}"
    
    def _validate_media_file(self, file_path: Path, is_video: bool = False) -> None:
        """Validate media file format and size."""
        # Check if file exists
        if not file_path.exists():
            raise AudioUploadError(f"File not found: {file_path}")
        
        # Check file size
        file_size = file_path.stat().st_size
        max_size = self.settings.max_video_file_size if is_video else self.settings.max_audio_file_size
        allowed_formats = self.settings.allowed_video_formats if is_video else self.settings.allowed_audio_formats
        media_type = "video" if is_video else "audio"
        
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            raise AudioUploadError(
                f"File size exceeds limit: {size_mb:.1f}MB > {max_mb}MB"
            )
        
        # Check file format
        file_extension = file_path.suffix.lower().lstrip('.')
        if file_extension not in allowed_formats:
            raise AudioUploadError(
                f"Unsupported {media_type} format: {file_extension}. "
                f"Allowed formats: {', '.join(allowed_formats)}"
            )
            
    def _validate_audio_file(self, file_path: Path) -> None:
        """Validate audio file format and size."""
        self._validate_media_file(file_path, is_video=False)
    
    async def upload_audio(self, file_path: Path) -> str:
        """
        Upload audio file to S3.
        
        Args:
            file_path: Path to the audio file to upload
            
        Returns:
            S3 key for the uploaded file
            
        Raises:
            AudioUploadError: If upload fails
        """
        try:
            # Validate file
            self._validate_audio_file(file_path)
            
            # Generate S3 key
            s3_key = self._generate_s3_key(file_path, self.settings.s3_audio_prefix)
            
            # Upload file to S3 in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._upload_file_sync,
                file_path,
                s3_key
            )
            
            return s3_key
            
        except Exception as e:
            if isinstance(e, AudioUploadError):
                raise
            raise AudioUploadError(f"S3 upload failed: {str(e)}")
    
    async def upload_video(self, file_path: Path) -> str:
        """
        Upload video file to S3.
        
        Args:
            file_path: Path to the video file to upload
            
        Returns:
            S3 key for the uploaded file
            
        Raises:
            AudioUploadError: If upload fails
        """
        try:
            # Validate file
            self._validate_media_file(file_path, is_video=True)
            
            # Generate S3 key with video prefix
            s3_key = self._generate_s3_key(file_path, self.settings.s3_video_prefix)
            
            # Upload file to S3 in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._upload_video_file_sync,
                file_path,
                s3_key
            )
            
            return s3_key
            
        except Exception as e:
            if isinstance(e, AudioUploadError):
                raise
            raise AudioUploadError(f"S3 video upload failed: {str(e)}")
    
    def _upload_video_file_sync(self, file_path: Path, s3_key: str) -> None:
        """Synchronous video file upload to S3."""
        try:
            self.s3_client.upload_file(
                str(file_path),
                self.settings.s3_bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': self._get_content_type(file_path, True),
                    'ServerSideEncryption': 'AES256'
                }
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise AudioUploadError(f"S3 bucket not found: {self.settings.s3_bucket_name}")
            elif error_code == 'AccessDenied':
                raise AudioUploadError("Access denied to S3 bucket")
            else:
                raise AudioUploadError(f"S3 upload error: {error_code}")
        except NoCredentialsError:
            raise AudioUploadError("AWS credentials not configured")
    
    def _upload_file_sync(self, file_path: Path, s3_key: str) -> None:
        """Synchronous file upload to S3."""
        try:
            self.s3_client.upload_file(
                str(file_path),
                self.settings.s3_bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': self._get_content_type(file_path, False),
                    'ServerSideEncryption': 'AES256'
                }
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise AudioUploadError(f"S3 bucket not found: {self.settings.s3_bucket_name}")
            elif error_code == 'AccessDenied':
                raise AudioUploadError("Access denied to S3 bucket")
            else:
                raise AudioUploadError(f"S3 upload error: {error_code}")
        except NoCredentialsError:
            raise AudioUploadError("AWS credentials not configured")
    
    def _get_content_type(self, file_path: Path, is_video: bool = False) -> str:
        """Get MIME content type for media file."""
        extension = file_path.suffix.lower()
        if is_video:
            content_types = {
                '.mp4': 'video/mp4',
                '.webm': 'video/webm',
                '.mov': 'video/quicktime',
                '.avi': 'video/x-msvideo',
            }
        else:
            content_types = {
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.m4a': 'audio/mp4',
                '.mp4': 'audio/mp4',
                '.webm': 'audio/webm',
                '.ogg': 'audio/ogg',
            }
        return content_types.get(extension, 'application/octet-stream')
    
    async def get_audio_url(
        self, 
        s3_key: str, 
        expiry_seconds: Optional[int] = None
    ) -> str:
        """
        Generate a presigned URL for audio file download.
        
        Args:
            s3_key: S3 key for the audio file
            expiry_seconds: URL expiry time in seconds
            
        Returns:
            Presigned URL for downloading the file
            
        Raises:
            AudioNotFoundError: If file doesn't exist
        """
        try:
            if expiry_seconds is None:
                expiry_seconds = self.settings.s3_presigned_url_expiry
            
            # Check if object exists first
            loop = asyncio.get_event_loop()
            exists = await loop.run_in_executor(
                None,
                self._check_object_exists,
                s3_key
            )
            
            if not exists:
                raise AudioNotFoundError(f"Audio file not found: {s3_key}")
            
            # Generate presigned URL
            url = await loop.run_in_executor(
                None,
                self._generate_presigned_url,
                s3_key,
                expiry_seconds
            )
            
            return url
            
        except AudioNotFoundError:
            raise
        except Exception as e:
            raise AudioNotFoundError(f"Failed to generate URL: {str(e)}")

    async def get_video_url(
        self, 
        s3_key: str, 
        expiry_seconds: Optional[int] = None
    ) -> str:
        """
        Generate a presigned URL for video file download.
        
        Args:
            s3_key: S3 key for the video file
            expiry_seconds: URL expiry time in seconds
            
        Returns:
            Presigned URL for downloading the file
            
        Raises:
            AudioNotFoundError: If file doesn't exist
        """
        try:
            if expiry_seconds is None:
                expiry_seconds = self.settings.s3_presigned_url_expiry
            
            # Check if object exists first
            loop = asyncio.get_event_loop()
            exists = await loop.run_in_executor(
                None,
                self._check_object_exists,
                s3_key
            )
            
            if not exists:
                raise AudioNotFoundError(f"Video file not found: {s3_key}")
            
            # Generate presigned URL
            url = await loop.run_in_executor(
                None,
                self._generate_presigned_url,
                s3_key,
                expiry_seconds
            )
            
            return url
            
        except AudioNotFoundError:
            raise
        except Exception as e:
            raise AudioNotFoundError(f"Failed to generate video URL: {str(e)}")
    
    def _check_object_exists(self, s3_key: str) -> bool:
        """Check if S3 object exists."""
        try:
            self.s3_client.head_object(
                Bucket=self.settings.s3_bucket_name,
                Key=s3_key
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    def _generate_presigned_url(self, s3_key: str, expiry_seconds: int) -> str:
        """Generate presigned URL synchronously."""
        try:
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.settings.s3_bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiry_seconds
            )
        except ClientError as e:
            raise Exception(f"Failed to generate presigned URL: {e}")
    
    async def delete_audio(self, s3_key: str) -> bool:
        """
        Delete audio file from S3.
        
        Args:
            s3_key: S3 key for the audio file to delete
            
        Returns:
            True if deletion successful (or file didn't exist)
            
        Raises:
            Exception: If deletion fails due to permission or other errors
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._delete_object_sync,
                s3_key
            )
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # File doesn't exist, consider it successfully deleted
                return True
            elif error_code == 'AccessDenied':
                raise Exception("Access denied for S3 deletion")
            else:
                raise Exception(f"S3 deletion error: {error_code}")
        except Exception as e:
            raise Exception(f"Failed to delete audio file: {str(e)}")
    
    def _delete_object_sync(self, s3_key: str) -> None:
        """Delete S3 object synchronously."""
        self.s3_client.delete_object(
            Bucket=self.settings.s3_bucket_name,
            Key=s3_key
        )
    
    async def get_file_metadata(self, s3_key: str) -> dict:
        """
        Get metadata for an audio file in S3.
        
        Args:
            s3_key: S3 key for the audio file
            
        Returns:
            Dictionary containing file metadata
            
        Raises:
            AudioNotFoundError: If file doesn't exist
        """
        try:
            loop = asyncio.get_event_loop()
            metadata = await loop.run_in_executor(
                None,
                self._get_object_metadata_sync,
                s3_key
            )
            
            return {
                'size': metadata.get('ContentLength', 0),
                'content_type': metadata.get('ContentType', ''),
                'last_modified': metadata.get('LastModified'),
                'etag': metadata.get('ETag', '').strip('"'),
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise AudioNotFoundError(f"Audio file not found: {s3_key}")
            raise Exception(f"Failed to get file metadata: {e}")
    
    def _get_object_metadata_sync(self, s3_key: str) -> dict:
        """Get S3 object metadata synchronously."""
        response = self.s3_client.head_object(
            Bucket=self.settings.s3_bucket_name,
            Key=s3_key
        )
        return response