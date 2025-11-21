"""Media storage service that handles both local and S3 storage modes."""
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.config import Settings, MediaStorageMode
from app.services.s3 import S3Service, AudioUploadError, AudioNotFoundError


class MediaStorageService:
    """Service for managing media files based on storage mode configuration."""
    
    def __init__(self, settings: Settings):
        """Initialize media storage service."""
        self.settings = settings
        self.s3_service = S3Service(settings) if self._needs_s3() else None
    
    def _needs_s3(self) -> bool:
        """Check if S3 service is needed based on storage mode."""
        return self.settings.media_storage_mode in [
            MediaStorageMode.S3_ONLY,
            MediaStorageMode.LOCAL_WITH_S3
        ]
    
    def _get_local_path(self, filename: str) -> Path:
        """Generate local file path for storage."""
        if not self.settings.local_media_path:
            raise ValueError("local_media_path not configured")
        
        base_path = Path(self.settings.local_media_path)
        timestamp = datetime.now().strftime("%Y/%m/%d")
        unique_id = str(uuid4())[:8]
        
        file_path = base_path / timestamp
        file_path.mkdir(parents=True, exist_ok=True)
        
        return file_path / f"{unique_id}_{filename}"
    
    async def store_video(self, source_file: Path) -> dict:
        """
        Store video file based on configured storage mode.
        
        Args:
            source_file: Path to the video file to store
            
        Returns:
            Dictionary with storage information:
            - s3_key: S3 key if stored in S3 (optional)
            - local_path: Local path if stored locally (optional)
            - storage_mode: The storage mode used
            
        Raises:
            AudioUploadError: If storage fails
        """
        try:
            result = {
                "storage_mode": self.settings.media_storage_mode.value
            }
            
            if self.settings.media_storage_mode == MediaStorageMode.S3_ONLY:
                # Store only in S3 (use video prefix)
                s3_key = await self.s3_service.upload_video(source_file)
                result["s3_key"] = s3_key
                
            elif self.settings.media_storage_mode == MediaStorageMode.LOCAL_WITH_S3:
                # Store in both local and S3
                local_path = self._get_local_path(source_file.name)
                
                # Copy to local storage
                await asyncio.to_thread(shutil.copy2, source_file, local_path)
                result["local_path"] = str(local_path)
                
                # Also upload to S3
                s3_key = await self.s3_service.upload_video(source_file)
                result["s3_key"] = s3_key
            
            return result
            
        except Exception as e:
            raise AudioUploadError(f"Video storage failed: {str(e)}")
    
    async def store_audio(self, source_file: Path) -> dict:
        """
        Store audio file based on configured storage mode.
        
        Args:
            source_file: Path to the audio file to store
            
        Returns:
            Dictionary with storage information:
            - s3_key: S3 key if stored in S3 (optional)
            - local_path: Local path if stored locally (optional)
            - storage_mode: The storage mode used
            
        Raises:
            AudioUploadError: If storage fails
        """
        try:
            result = {
                "storage_mode": self.settings.media_storage_mode.value
            }
            
            if self.settings.media_storage_mode == MediaStorageMode.S3_ONLY:
                # Store only in S3
                s3_key = await self.s3_service.upload_audio(source_file)
                result["s3_key"] = s3_key
                
            elif self.settings.media_storage_mode == MediaStorageMode.LOCAL_WITH_S3:
                # Store in both local and S3
                local_path = self._get_local_path(source_file.name)
                
                # Copy to local storage
                await asyncio.to_thread(shutil.copy2, source_file, local_path)
                result["local_path"] = str(local_path)
                
                # Also upload to S3
                s3_key = await self.s3_service.upload_audio(source_file)
                result["s3_key"] = s3_key
            
            return result
            
        except Exception as e:
            raise AudioUploadError(f"Media storage failed: {str(e)}")
    
    async def get_audio_url(self, s3_key: Optional[str] = None, local_path: Optional[str] = None) -> str:
        """
        Get URL for audio playback based on storage mode.
        
        Args:
            s3_key: S3 key for the audio file (optional)
            local_path: Local path for the audio file (optional)
            
        Returns:
            URL for audio playback
            
        Raises:
            AudioNotFoundError: If audio file is not accessible
        """
        try:
            if self.settings.media_storage_mode == MediaStorageMode.S3_ONLY:
                if not s3_key:
                    raise AudioNotFoundError("S3 key required for S3-only mode")
                return await self.s3_service.get_audio_url(s3_key)
                
            elif self.settings.media_storage_mode == MediaStorageMode.LOCAL_WITH_S3:
                # Prefer local file if it exists, fallback to S3
                if local_path and Path(local_path).exists():
                    # Return relative path for local serving
                    # This assumes the app will serve local files via a route
                    return f"/media/local/{Path(local_path).name}"
                elif s3_key:
                    return await self.s3_service.get_audio_url(s3_key)
                else:
                    raise AudioNotFoundError("Neither local file nor S3 key available")
            
            raise AudioNotFoundError("Unsupported storage mode")
            
        except Exception as e:
            if isinstance(e, AudioNotFoundError):
                raise
            raise AudioNotFoundError(f"Failed to get audio URL: {str(e)}")
    
    async def delete_audio(self, s3_key: Optional[str] = None, local_path: Optional[str] = None) -> bool:
        """
        Delete audio file from configured storage.
        
        Args:
            s3_key: S3 key for the audio file (optional)
            local_path: Local path for the audio file (optional)
            
        Returns:
            True if deletion successful
        """
        success = True
        
        try:
            if self.settings.media_storage_mode == MediaStorageMode.S3_ONLY:
                if s3_key:
                    success = await self.s3_service.delete_audio(s3_key)
                    
            elif self.settings.media_storage_mode == MediaStorageMode.LOCAL_WITH_S3:
                # Delete from both local and S3
                if local_path:
                    local_file = Path(local_path)
                    if local_file.exists():
                        await asyncio.to_thread(local_file.unlink)
                
                if s3_key:
                    s3_success = await self.s3_service.delete_audio(s3_key)
                    success = success and s3_success
            
            return success
            
        except Exception as e:
            raise Exception(f"Failed to delete audio: {str(e)}")
    
    def get_file_path_for_processing(self, s3_key: Optional[str] = None, local_path: Optional[str] = None) -> Path:
        """
        Get the best file path for audio processing (transcription, etc.).
        
        Args:
            s3_key: S3 key for the audio file (optional)
            local_path: Local path for the audio file (optional)
            
        Returns:
            Path to file for processing
            
        Raises:
            AudioNotFoundError: If no accessible file found
        """
        if self.settings.media_storage_mode == MediaStorageMode.LOCAL_WITH_S3:
            # Prefer local file for processing to avoid download
            if local_path and Path(local_path).exists():
                return Path(local_path)
        
        # For S3-only mode or if local file not available, will need to download
        # This should be handled by the audio processor workflow
        if s3_key:
            return None  # Indicates S3 download needed
        
        raise AudioNotFoundError("No accessible file for processing")