"""DBOS workflows for audio processing pipeline."""
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID
import tempfile
import os

from dbos import DBOS
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.log_entry import LogEntry, ProcessingStatus
from app.services.s3 import S3Service
from app.services.media_storage import MediaStorageService
from app.services.openai_client import OpenAIService
from app.services.video_processor import VideoProcessor, VideoProcessingError

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Exception raised when workflow step fails."""
    pass


class BaseWorkflowStep:
    """Base class for workflow steps."""
    
    def __init__(self, workflow_instance: 'AudioProcessingWorkflow'):
        self.workflow = workflow_instance
        self.settings = workflow_instance.settings
        self.db_session = workflow_instance.db_session
        self.media_storage = workflow_instance.media_storage
        self.openai_service = workflow_instance.openai_service


class VideoPreprocessStep(BaseWorkflowStep):
    """Workflow step for preprocessing video files to extract audio."""
    
    def __init__(self, workflow_instance: 'AudioProcessingWorkflow'):
        super().__init__(workflow_instance)
        self.video_processor = VideoProcessor()
    
    async def execute(self, media_file: Path) -> Dict[str, Any]:
        """
        Execute video preprocessing step.
        
        Args:
            media_file: Path to media file (video or audio)
            
        Returns:
            Dictionary with preprocessing results including audio file path
            
        Raises:
            WorkflowError: If preprocessing fails
        """
        try:
            logger.info(f"Starting media preprocessing for: {media_file}")
            
            # Validate file exists
            if not media_file.exists():
                raise WorkflowError(f"File not found: {media_file}")
            
            # Check if this is a video file
            if self.video_processor.is_video_file(media_file):
                logger.info("Video file detected - extracting audio")
                
                # Get video information
                video_info = await self.video_processor.get_video_info(media_file)
                
                if not video_info.get('has_audio', False):
                    raise WorkflowError("Video file contains no audio track")
                
                # Extract audio from video
                audio_file = await self.video_processor.extract_audio_from_video(
                    media_file,
                    output_format="wav",
                    sample_rate=44100
                )
                
                logger.info(f"Audio extracted from video: {audio_file}")
                
                return {
                    "success": True,
                    "audio_file": audio_file,
                    "original_file": media_file,
                    "video_file": media_file,  # Keep reference to original video
                    "is_video": True,
                    "video_info": video_info,
                    "extracted_audio": True
                }
            else:
                logger.info("Audio file detected - no preprocessing needed")
                return {
                    "success": True,
                    "audio_file": media_file,
                    "original_file": media_file,
                    "video_file": None,  # No video file for audio-only
                    "is_video": False,
                    "extracted_audio": False
                }
            
        except VideoProcessingError as e:
            logger.error(f"Video preprocessing failed: {e}")
            raise WorkflowError(f"Video preprocessing failed: {str(e)}")
        except Exception as e:
            logger.error(f"Media preprocessing failed: {e}")
            raise WorkflowError(f"Media preprocessing failed: {str(e)}")


class StoreVideoStep(BaseWorkflowStep):
    """Workflow step for storing video files based on configuration."""
    
    async def execute(self, video_file: Path) -> Dict[str, Any]:
        """
        Execute video storage step.
        
        Args:
            video_file: Path to video file to store
            
        Returns:
            Dictionary with storage results
            
        Raises:
            WorkflowError: If storage fails
        """
        try:
            logger.info(f"Starting video storage for: {video_file}")
            
            # Validate file exists
            if not video_file.exists():
                raise WorkflowError(f"File not found: {video_file}")
            
            # Store video using media storage service
            storage_result = await self.media_storage.store_video(video_file)
            
            logger.info(f"Successfully stored video: {storage_result}")
            return {
                "success": True,
                "file_size": video_file.stat().st_size,
                **storage_result
            }
            
        except Exception as e:
            logger.error(f"Video storage failed: {e}")
            raise WorkflowError(f"Video storage failed: {str(e)}")


class StoreAudioStep(BaseWorkflowStep):
    """Workflow step for storing audio based on configuration."""
    
    async def execute(self, audio_file: Path) -> Dict[str, Any]:
        """
        Execute audio storage step.
        
        Args:
            audio_file: Path to audio file to store
            
        Returns:
            Dictionary with storage results
            
        Raises:
            WorkflowError: If storage fails
        """
        try:
            logger.info(f"Starting audio storage for: {audio_file}")
            
            # Validate file exists
            if not audio_file.exists():
                raise WorkflowError(f"File not found: {audio_file}")
            
            # Store audio using media storage service
            storage_result = await self.media_storage.store_audio(audio_file)
            
            logger.info(f"Successfully stored audio: {storage_result}")
            return {
                "success": True,
                "file_size": audio_file.stat().st_size,
                **storage_result
            }
            
        except Exception as e:
            logger.error(f"Audio storage failed: {e}")
            raise WorkflowError(f"Audio storage failed: {str(e)}")


class TranscribeAudioStep(BaseWorkflowStep):
    """Workflow step for transcribing audio using OpenAI."""
    
    async def execute(
        self, 
        audio_file: Optional[Path] = None,
        s3_key: Optional[str] = None,
        local_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute audio transcription step.
        
        Args:
            audio_file: Local audio file path (optional)
            s3_key: S3 key for audio file (optional)
            local_path: Local file path for audio file (optional)
            
        Returns:
            Dictionary with transcription results
            
        Raises:
            WorkflowError: If transcription fails
        """
        try:
            logger.info("Starting audio transcription")
            
            # Determine the best file path for transcription
            if not audio_file:
                # Use media storage service to get the best file path
                file_path = self.media_storage.get_file_path_for_processing(s3_key, local_path)
                if file_path is None:
                    # Need to download from S3
                    audio_file = await self._download_from_s3(s3_key)
                else:
                    audio_file = file_path
            
            if not audio_file or not audio_file.exists():
                raise WorkflowError("No valid audio file for transcription")
            
            # Transcribe audio
            transcription = await self.openai_service.transcribe_audio(
                audio_file,
                prompt="Captain's log entry from sailing vessel"
            )
            
            logger.info(f"Successfully transcribed audio: {len(transcription)} characters")
            return {
                "success": True,
                "transcription": transcription,
                "character_count": len(transcription)
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise WorkflowError(f"Transcription failed: {str(e)}")
        
        finally:
            # Clean up temporary file if downloaded from S3
            if s3_key and audio_file and audio_file.name.startswith('/tmp'):
                try:
                    audio_file.unlink()
                except:
                    pass
    
    async def _download_from_s3(self, s3_key: str) -> Path:
        """Download audio file from S3 to temporary file."""
        # Get presigned URL
        url = await self.s3_service.get_audio_url(s3_key)
        
        # Download file to temporary location
        import aiohttp
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise WorkflowError(f"Failed to download audio from S3: {response.status}")
                    
                    async for chunk in response.content.iter_chunked(8192):
                        tmp_file.write(chunk)
            
            return Path(tmp_file.name)


class GenerateEmbeddingStep(BaseWorkflowStep):
    """Workflow step for generating embeddings from transcription."""
    
    async def execute(self, transcription: str) -> Dict[str, Any]:
        """
        Execute embedding generation step.
        
        Args:
            transcription: Transcribed text to generate embedding for
            
        Returns:
            Dictionary with embedding results
            
        Raises:
            WorkflowError: If embedding generation fails
        """
        try:
            logger.info("Starting embedding generation")
            
            # Validate input
            if not transcription or not transcription.strip():
                raise WorkflowError("Empty transcription provided for embedding")
            
            # Generate embedding
            embedding = await self.openai_service.generate_embedding(transcription)
            
            logger.info(f"Successfully generated embedding: {len(embedding)} dimensions")
            return {
                "success": True,
                "embedding": embedding,
                "embedding_dimensions": len(embedding)
            }
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise WorkflowError(f"Embedding generation failed: {str(e)}")


class GenerateSummaryStep(BaseWorkflowStep):
    """Workflow step for generating summary from transcription."""
    
    async def execute(self, transcription: str) -> Dict[str, Any]:
        """
        Execute summary generation step.
        
        Args:
            transcription: Transcribed text to summarize
            
        Returns:
            Dictionary with summary results
            
        Raises:
            WorkflowError: If summary generation fails
        """
        try:
            logger.info("Starting summary generation")
            
            # Validate input
            if not transcription or not transcription.strip():
                raise WorkflowError("Empty transcription provided for summary")
            
            # Generate summary
            summary = await self.openai_service.generate_summary(
                transcription,
                instructions="Report operational status, environmental conditions, navigational data, and significant events."
            )
            
            logger.info(f"Successfully generated summary: {len(summary)} characters")
            return {
                "success": True,
                "summary": summary,
                "summary_length": len(summary)
            }
            
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            raise WorkflowError(f"Summary generation failed: {str(e)}")


class UpdateLogEntryStep(BaseWorkflowStep):
    """Workflow step for updating log entry in database."""
    
    async def execute(self, log_entry_id: UUID, **update_data) -> Dict[str, Any]:
        """
        Execute log entry update step.
        
        Args:
            log_entry_id: UUID of log entry to update
            **update_data: Fields to update
            
        Returns:
            Dictionary with update results
            
        Raises:
            WorkflowError: If update fails
        """
        try:
            logger.info(f"Updating log entry: {log_entry_id}")
            
            # Get log entry
            result = await self.db_session.get(LogEntry, log_entry_id)
            if not result:
                raise WorkflowError(f"Log entry not found: {log_entry_id}")
            
            log_entry = result
            
            # Update fields
            for field, value in update_data.items():
                if hasattr(log_entry, field):
                    setattr(log_entry, field, value)
            
            # Commit changes
            await self.db_session.commit()
            await self.db_session.refresh(log_entry)
            
            logger.info(f"Successfully updated log entry: {log_entry_id}")
            return {
                "success": True,
                "log_entry_id": str(log_entry_id),
                "updated_fields": list(update_data.keys())
            }
            
        except WorkflowError:
            raise
        except Exception as e:
            logger.error(f"Log entry update failed: {e}")
            await self.db_session.rollback()
            raise WorkflowError(f"Log entry update failed: {str(e)}")


class AudioProcessingWorkflow:
    """Main workflow for processing media files (audio and video)."""
    
    def __init__(
        self,
        settings: Settings,
        db_session: AsyncSession,
        media_storage: Optional[MediaStorageService] = None,
        openai_service: Optional[OpenAIService] = None
    ):
        """Initialize workflow with required services."""
        self.settings = settings
        self.db_session = db_session
        self.media_storage = media_storage or MediaStorageService(settings)
        self.openai_service = openai_service or OpenAIService(settings)
        
        # Initialize workflow steps
        self.preprocess_step = VideoPreprocessStep(self)
        self.store_video_step = StoreVideoStep(self)
        self.store_audio_step = StoreAudioStep(self)
        self.transcribe_step = TranscribeAudioStep(self)
        self.embedding_step = GenerateEmbeddingStep(self)
        self.summary_step = GenerateSummaryStep(self)
        self.update_step = UpdateLogEntryStep(self)
    
    async def process_media(
        self, 
        log_entry_id: UUID, 
        media_file: Path,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Process media file (audio or video) through complete pipeline.
        
        Args:
            log_entry_id: UUID of log entry to update
            media_file: Path to media file to process (audio or video)
            max_retries: Maximum number of retries for transient failures
            
        Returns:
            Dictionary with processing results
            
        Raises:
            WorkflowError: If processing fails
        """
        results = {
            "log_entry_id": str(log_entry_id),
            "success": False,
            "steps_completed": [],
            "error": None,
            "extracted_audio_file": None
        }
        
        try:
            logger.info(f"Starting media processing workflow for: {log_entry_id}")
            
            # Step 1: Update status to transcribing
            await self._update_status(log_entry_id, ProcessingStatus.TRANSCRIBING)
            
            # Step 2: Preprocess media file (extract audio if video)
            preprocess_result = await self._retry_step(
                "preprocess",
                self.preprocess_step.execute,
                media_file,
                max_retries=max_retries
            )
            results.update(preprocess_result)
            results["steps_completed"].append("preprocess")
            
            # Get the audio file to use for transcription
            audio_file = preprocess_result["audio_file"]
            video_file = preprocess_result.get("video_file")
            is_video = preprocess_result.get("is_video", False)
            results["extracted_audio_file"] = str(audio_file) if preprocess_result.get("extracted_audio") else None
            
            # Step 3a: Store video file if this is a video
            video_update_data = {}
            if is_video and video_file:
                video_store_result = await self._retry_step(
                    "store_video", 
                    self.store_video_step.execute, 
                    video_file,
                    max_retries=max_retries
                )
                results.update({"video_" + k: v for k, v in video_store_result.items()})
                results["steps_completed"].append("store_video")
                
                # Prepare video storage info for database
                if "s3_key" in video_store_result:
                    video_update_data["video_s3_key"] = video_store_result["s3_key"]
                if "local_path" in video_store_result:
                    video_update_data["video_local_path"] = video_store_result["local_path"]
            
            # Step 3b: Store audio
            audio_store_result = await self._retry_step(
                "store_audio", 
                self.store_audio_step.execute, 
                audio_file,
                max_retries=max_retries
            )
            results.update({"audio_" + k: v for k, v in audio_store_result.items()})
            results["steps_completed"].append("store_audio")
            
            # Update log entry with storage info
            update_data = {**video_update_data}
            if "s3_key" in audio_store_result:
                update_data["audio_s3_key"] = audio_store_result["s3_key"]
            if "local_path" in audio_store_result:
                update_data["audio_local_path"] = audio_store_result["local_path"]
            
            await self.update_step.execute(log_entry_id, **update_data)
            
            # Step 4: Transcribe audio
            transcribe_result = await self._retry_step(
                "transcribe",
                self.transcribe_step.execute,
                audio_file=audio_file,
                s3_key=audio_store_result.get("s3_key"),
                local_path=audio_store_result.get("local_path"),
                max_retries=max_retries
            )
            results.update(transcribe_result)
            results["steps_completed"].append("transcribe")
            
            # Step 5: Update status to vectorizing
            await self._update_status(log_entry_id, ProcessingStatus.VECTORIZING)
            
            # Step 6: Generate embedding
            embedding_result = await self._retry_step(
                "embedding",
                self.embedding_step.execute,
                transcribe_result["transcription"],
                max_retries=max_retries
            )
            results.update(embedding_result)
            results["steps_completed"].append("embedding")
            
            # Step 7: Update status to summarizing
            await self._update_status(log_entry_id, ProcessingStatus.SUMMARIZING)
            
            # Step 8: Generate summary
            summary_result = await self._retry_step(
                "summary",
                self.summary_step.execute,
                transcribe_result["transcription"],
                max_retries=max_retries
            )
            results.update(summary_result)
            results["steps_completed"].append("summary")
            
            # Step 9: Update log entry with all results
            await self.update_step.execute(
                log_entry_id,
                transcription=transcribe_result["transcription"],
                embedding=embedding_result["embedding"],
                summary=summary_result["summary"],
                processing_status=ProcessingStatus.COMPLETED,
                processing_error=None
            )
            results["steps_completed"].append("update")
            
            results["success"] = True
            logger.info(f"Media processing completed successfully: {log_entry_id}")
            
            return results
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Media processing failed: {error_msg}")
            results["error"] = error_msg
            
            # Update log entry with error status
            try:
                await self.update_step.execute(
                    log_entry_id,
                    processing_status=ProcessingStatus.FAILED,
                    processing_error=error_msg
                )
            except Exception as update_error:
                logger.error(f"Failed to update error status: {update_error}")
            
            raise WorkflowError(f"Media processing failed: {error_msg}")
        
        finally:
            # Clean up extracted audio file if it was created during preprocessing
            # but do NOT clean up the original video file since we've stored it
            if results.get("extracted_audio_file"):
                try:
                    extracted_path = Path(results["extracted_audio_file"])
                    if extracted_path.exists():
                        extracted_path.unlink()
                        logger.info("Cleaned up extracted audio file")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up extracted audio file: {cleanup_error}")
    
    # Keep the old method name for backward compatibility
    async def process_audio(self, log_entry_id: UUID, audio_file: Path, max_retries: int = 3) -> Dict[str, Any]:
        """Legacy method - redirects to process_media."""
        return await self.process_media(log_entry_id, audio_file, max_retries)
    
    async def _retry_step(
        self, 
        step_name: str, 
        step_func, 
        *args, 
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """Retry a workflow step with exponential backoff."""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Executing {step_name} step (attempt {attempt + 1})")
                return await step_func(*args, **kwargs)
                
            except Exception as e:
                last_exception = e
                logger.warning(f"{step_name} step failed (attempt {attempt + 1}): {e}")
                
                # Don't retry on certain errors
                if isinstance(e, (ValueError, FileNotFoundError)):
                    raise
                
                # Exponential backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying {step_name} step in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
        
        # All retries failed
        raise WorkflowError(
            f"{step_name} step failed after {max_retries} attempts: {last_exception}"
        )
    
    async def _update_status(self, log_entry_id: UUID, status: ProcessingStatus) -> None:
        """Update log entry processing status."""
        try:
            await self.update_step.execute(log_entry_id, processing_status=status)
        except Exception as e:
            logger.warning(f"Failed to update status to {status}: {e}")
            # Don't fail the whole workflow for status updates


# DBOS workflow decorators (when using DBOS in production)
@DBOS.workflow()
async def process_audio_workflow(
    log_entry_id: str,
    audio_file_path: str,
    settings_dict: dict
) -> dict:
    """
    DBOS workflow wrapper for audio processing.
    
    This function provides the DBOS workflow interface for the audio processing pipeline.
    In production, this would be the entry point for workflow execution.
    """
    # Reconstruct objects from serializable data
    settings = Settings(**settings_dict)
    
    # This would need proper dependency injection in a real implementation
    # For now, this is a placeholder that shows the intended structure
    
    return {
        "workflow_id": log_entry_id,
        "status": "completed",
        "message": "Audio processing workflow executed successfully"
    }


@DBOS.step()
async def upload_audio_step(audio_file_path: str, settings_dict: dict) -> dict:
    """DBOS step for audio upload."""
    # Implementation would go here
    return {"s3_key": "audio/example.wav"}


@DBOS.step()
async def transcribe_audio_step(s3_key: str, settings_dict: dict) -> dict:
    """DBOS step for audio transcription."""
    # Implementation would go here
    return {"transcription": "Example transcription"}


@DBOS.step()
async def generate_embedding_step(transcription: str, settings_dict: dict) -> dict:
    """DBOS step for embedding generation."""
    # Implementation would go here
    return {"embedding": [0.1] * 1536}


@DBOS.step()
async def generate_summary_step(transcription: str, settings_dict: dict) -> dict:
    """DBOS step for summary generation."""
    # Implementation would go here
    return {"summary": "Example summary"}


@DBOS.step()
async def update_log_entry_step(log_entry_id: str, update_data: dict) -> dict:
    """DBOS step for log entry update."""
    # Implementation would go here
    return {"success": True}