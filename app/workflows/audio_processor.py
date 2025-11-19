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
from app.services.openai_client import OpenAIService

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
        self.s3_service = workflow_instance.s3_service
        self.openai_service = workflow_instance.openai_service


class UploadToS3Step(BaseWorkflowStep):
    """Workflow step for uploading audio to S3."""
    
    async def execute(self, audio_file: Path) -> Dict[str, Any]:
        """
        Execute S3 upload step.
        
        Args:
            audio_file: Path to audio file to upload
            
        Returns:
            Dictionary with upload results
            
        Raises:
            WorkflowError: If upload fails
        """
        try:
            logger.info(f"Starting S3 upload for: {audio_file}")
            
            # Validate file exists
            if not audio_file.exists():
                raise WorkflowError(f"File not found: {audio_file}")
            
            # Upload to S3
            s3_key = await self.s3_service.upload_audio(audio_file)
            
            logger.info(f"Successfully uploaded to S3: {s3_key}")
            return {
                "success": True,
                "s3_key": s3_key,
                "file_size": audio_file.stat().st_size
            }
            
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            raise WorkflowError(f"S3 upload failed: {str(e)}")


class TranscribeAudioStep(BaseWorkflowStep):
    """Workflow step for transcribing audio using OpenAI."""
    
    async def execute(
        self, 
        audio_file: Optional[Path] = None,
        s3_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute audio transcription step.
        
        Args:
            audio_file: Local audio file path (optional)
            s3_key: S3 key for audio file (optional)
            
        Returns:
            Dictionary with transcription results
            
        Raises:
            WorkflowError: If transcription fails
        """
        try:
            logger.info("Starting audio transcription")
            
            # If S3 key provided, download file first
            if s3_key and not audio_file:
                audio_file = await self._download_from_s3(s3_key)
            
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
                instructions="Focus on key events, weather conditions, and important decisions."
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
    """Main workflow for processing audio files."""
    
    def __init__(
        self,
        settings: Settings,
        db_session: AsyncSession,
        s3_service: Optional[S3Service] = None,
        openai_service: Optional[OpenAIService] = None
    ):
        """Initialize workflow with required services."""
        self.settings = settings
        self.db_session = db_session
        self.s3_service = s3_service or S3Service(settings)
        self.openai_service = openai_service or OpenAIService(settings)
        
        # Initialize workflow steps
        self.upload_step = UploadToS3Step(self)
        self.transcribe_step = TranscribeAudioStep(self)
        self.embedding_step = GenerateEmbeddingStep(self)
        self.summary_step = GenerateSummaryStep(self)
        self.update_step = UpdateLogEntryStep(self)
    
    async def process_audio(
        self, 
        log_entry_id: UUID, 
        audio_file: Path,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Process audio file through complete pipeline.
        
        Args:
            log_entry_id: UUID of log entry to update
            audio_file: Path to audio file to process
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
            "error": None
        }
        
        try:
            logger.info(f"Starting audio processing workflow for: {log_entry_id}")
            
            # Step 1: Update status to transcribing
            await self._update_status(log_entry_id, ProcessingStatus.TRANSCRIBING)
            
            # Step 2: Upload to S3
            upload_result = await self._retry_step(
                "upload", 
                self.upload_step.execute, 
                audio_file,
                max_retries=max_retries
            )
            results.update(upload_result)
            results["steps_completed"].append("upload")
            
            # Update log entry with S3 key
            await self.update_step.execute(
                log_entry_id,
                audio_s3_key=upload_result["s3_key"]
            )
            
            # Step 3: Transcribe audio
            transcribe_result = await self._retry_step(
                "transcribe",
                self.transcribe_step.execute,
                audio_file=audio_file,
                max_retries=max_retries
            )
            results.update(transcribe_result)
            results["steps_completed"].append("transcribe")
            
            # Step 4: Update status to vectorizing
            await self._update_status(log_entry_id, ProcessingStatus.VECTORIZING)
            
            # Step 5: Generate embedding
            embedding_result = await self._retry_step(
                "embedding",
                self.embedding_step.execute,
                transcribe_result["transcription"],
                max_retries=max_retries
            )
            results.update(embedding_result)
            results["steps_completed"].append("embedding")
            
            # Step 6: Update status to summarizing
            await self._update_status(log_entry_id, ProcessingStatus.SUMMARIZING)
            
            # Step 7: Generate summary
            summary_result = await self._retry_step(
                "summary",
                self.summary_step.execute,
                transcribe_result["transcription"],
                max_retries=max_retries
            )
            results.update(summary_result)
            results["steps_completed"].append("summary")
            
            # Step 8: Update log entry with all results
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
            logger.info(f"Audio processing completed successfully: {log_entry_id}")
            
            return results
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Audio processing failed: {error_msg}")
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
            
            raise WorkflowError(f"Audio processing failed: {error_msg}")
    
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