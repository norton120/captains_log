"""Network-resilient processor for handling intermittent connectivity issues."""
import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
import json

from dbos import DBOS
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.log_entry import LogEntry, ProcessingStatus
from app.services.s3 import S3Service, AudioUploadError
from app.services.openai_client import OpenAIService, TranscriptionError, EmbeddingError, SummaryError

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of network-dependent tasks."""
    S3_UPLOAD = "s3_upload"
    TRANSCRIPTION = "transcription"
    EMBEDDING = "embedding"
    SUMMARY = "summary"


class TaskPriority(Enum):
    """Task execution priority levels."""
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class NetworkTask:
    """Represents a network-dependent task that can be queued."""
    
    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        priority: TaskPriority,
        log_entry_id: str,
        payload: Dict[str, Any],
        max_retries: int = 10,
        created_at: Optional[datetime] = None
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.priority = priority
        self.log_entry_id = log_entry_id
        self.payload = payload
        self.max_retries = max_retries
        self.retry_count = 0
        self.created_at = created_at or datetime.utcnow()
        self.last_attempt = None
        self.error_message = None
        self.is_completed = False
        self.next_retry_at = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "priority": self.priority.value,
            "log_entry_id": self.log_entry_id,
            "payload": self.payload,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "error_message": self.error_message,
            "is_completed": self.is_completed,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NetworkTask':
        """Deserialize task from dictionary."""
        task = cls(
            task_id=data["task_id"],
            task_type=TaskType(data["task_type"]),
            priority=TaskPriority(data["priority"]),
            log_entry_id=data["log_entry_id"],
            payload=data["payload"],
            max_retries=data["max_retries"]
        )
        
        task.retry_count = data["retry_count"]
        task.created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        task.last_attempt = datetime.fromisoformat(data["last_attempt"]) if data.get("last_attempt") else None
        task.error_message = data.get("error_message")
        task.is_completed = data.get("is_completed", False)
        task.next_retry_at = datetime.fromisoformat(data["next_retry_at"]) if data.get("next_retry_at") else None
        
        return task

    def should_retry(self) -> bool:
        """Check if task should be retried."""
        if self.is_completed or self.retry_count >= self.max_retries:
            return False
        
        if self.next_retry_at and datetime.utcnow() < self.next_retry_at:
            return False
            
        return True

    def calculate_next_retry(self) -> None:
        """Calculate next retry time with exponential backoff."""
        # Start with 30 seconds, max out at 1 hour
        base_delay = 30
        max_delay = 3600
        
        delay = min(base_delay * (2 ** self.retry_count), max_delay)
        self.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)

    def mark_attempt(self, error_message: Optional[str] = None) -> None:
        """Mark a retry attempt."""
        self.last_attempt = datetime.utcnow()
        self.retry_count += 1
        self.error_message = error_message
        
        if error_message:
            self.calculate_next_retry()

    def mark_completed(self) -> None:
        """Mark task as completed."""
        self.is_completed = True
        self.next_retry_at = None
        self.error_message = None


class NetworkResilientProcessor:
    """Processor that handles network failures gracefully with task queuing."""
    
    def __init__(
        self, 
        settings: Settings,
        db_session: AsyncSession,
        s3_service: Optional[S3Service] = None,
        openai_service: Optional[OpenAIService] = None
    ):
        self.settings = settings
        self.db_session = db_session
        self.s3_service = s3_service or S3Service(settings)
        self.openai_service = openai_service or OpenAIService(settings)
        
        # In-memory task queue (in production, use Redis or database)
        self.task_queue: Dict[str, NetworkTask] = {}
        self._queue_lock = asyncio.Lock()
        
        # Task processing state
        self._processing = False
        self._processor_task = None

    async def start_processor(self) -> None:
        """Start the background task processor."""
        if not self._processing:
            self._processing = True
            self._processor_task = asyncio.create_task(self._process_queue_loop())
            logger.info("Network-resilient processor started")

    async def stop_processor(self) -> None:
        """Stop the background task processor."""
        self._processing = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            logger.info("Network-resilient processor stopped")

    async def queue_s3_upload(
        self, 
        log_entry_id: str, 
        file_path: Path,
        is_video: bool = False,
        priority: TaskPriority = TaskPriority.HIGH
    ) -> str:
        """Queue S3 upload task."""
        task_id = f"s3_upload_{log_entry_id}_{datetime.utcnow().timestamp()}"
        
        task = NetworkTask(
            task_id=task_id,
            task_type=TaskType.S3_UPLOAD,
            priority=priority,
            log_entry_id=log_entry_id,
            payload={
                "file_path": str(file_path),
                "is_video": is_video
            }
        )
        
        async with self._queue_lock:
            self.task_queue[task_id] = task
        
        logger.info(f"Queued S3 upload task: {task_id}")
        return task_id

    async def queue_transcription(
        self, 
        log_entry_id: str, 
        audio_file: Optional[Path] = None,
        s3_key: Optional[str] = None,
        local_path: Optional[str] = None,
        priority: TaskPriority = TaskPriority.HIGH
    ) -> str:
        """Queue transcription task."""
        task_id = f"transcription_{log_entry_id}_{datetime.utcnow().timestamp()}"
        
        task = NetworkTask(
            task_id=task_id,
            task_type=TaskType.TRANSCRIPTION,
            priority=priority,
            log_entry_id=log_entry_id,
            payload={
                "audio_file": str(audio_file) if audio_file else None,
                "s3_key": s3_key,
                "local_path": local_path
            }
        )
        
        async with self._queue_lock:
            self.task_queue[task_id] = task
        
        logger.info(f"Queued transcription task: {task_id}")
        return task_id

    async def queue_embedding_generation(
        self, 
        log_entry_id: str, 
        transcription: str,
        priority: TaskPriority = TaskPriority.MEDIUM
    ) -> str:
        """Queue embedding generation task."""
        task_id = f"embedding_{log_entry_id}_{datetime.utcnow().timestamp()}"
        
        task = NetworkTask(
            task_id=task_id,
            task_type=TaskType.EMBEDDING,
            priority=priority,
            log_entry_id=log_entry_id,
            payload={"transcription": transcription}
        )
        
        async with self._queue_lock:
            self.task_queue[task_id] = task
        
        logger.info(f"Queued embedding generation task: {task_id}")
        return task_id

    async def queue_summary_generation(
        self, 
        log_entry_id: str, 
        transcription: str,
        priority: TaskPriority = TaskPriority.MEDIUM
    ) -> str:
        """Queue summary generation task."""
        task_id = f"summary_{log_entry_id}_{datetime.utcnow().timestamp()}"
        
        task = NetworkTask(
            task_id=task_id,
            task_type=TaskType.SUMMARY,
            priority=priority,
            log_entry_id=log_entry_id,
            payload={"transcription": transcription}
        )
        
        async with self._queue_lock:
            self.task_queue[task_id] = task
        
        logger.info(f"Queued summary generation task: {task_id}")
        return task_id

    async def _process_queue_loop(self) -> None:
        """Background loop to process queued tasks."""
        while self._processing:
            try:
                await self._process_pending_tasks()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Error in queue processing loop: {e}")
                await asyncio.sleep(30)  # Wait longer on errors

    async def _process_pending_tasks(self) -> None:
        """Process all pending tasks in priority order."""
        # Get tasks that should be retried
        pending_tasks = []
        
        async with self._queue_lock:
            for task in self.task_queue.values():
                if task.should_retry():
                    pending_tasks.append(task)
        
        if not pending_tasks:
            return
        
        # Sort by priority and creation time
        pending_tasks.sort(key=lambda t: (t.priority.value, t.created_at))
        
        # Process tasks with concurrency limit
        semaphore = asyncio.Semaphore(3)  # Process max 3 tasks concurrently
        
        tasks = [
            self._process_task_with_semaphore(task, semaphore) 
            for task in pending_tasks[:10]  # Limit batch size
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_task_with_semaphore(self, task: NetworkTask, semaphore: asyncio.Semaphore) -> None:
        """Process a single task with semaphore control."""
        async with semaphore:
            await self._process_single_task(task)

    async def _process_single_task(self, task: NetworkTask) -> None:
        """Process a single network task."""
        try:
            logger.info(f"Processing task: {task.task_id} (attempt {task.retry_count + 1})")
            
            if task.task_type == TaskType.S3_UPLOAD:
                await self._execute_s3_upload(task)
            elif task.task_type == TaskType.TRANSCRIPTION:
                await self._execute_transcription(task)
            elif task.task_type == TaskType.EMBEDDING:
                await self._execute_embedding(task)
            elif task.task_type == TaskType.SUMMARY:
                await self._execute_summary(task)
            
            # Mark as completed
            task.mark_completed()
            logger.info(f"Task completed successfully: {task.task_id}")
            
        except Exception as e:
            error_msg = str(e)
            task.mark_attempt(error_msg)
            
            if task.retry_count >= task.max_retries:
                logger.error(f"Task failed permanently after {task.max_retries} attempts: {task.task_id} - {error_msg}")
                await self._mark_log_entry_failed(task.log_entry_id, error_msg)
            else:
                logger.warning(f"Task failed, will retry: {task.task_id} - {error_msg}")

    async def _execute_s3_upload(self, task: NetworkTask) -> None:
        """Execute S3 upload task."""
        payload = task.payload
        file_path = Path(payload["file_path"])
        is_video = payload.get("is_video", False)
        
        if is_video:
            s3_key = await self.s3_service.upload_video(file_path)
            update_field = "video_s3_key"
        else:
            s3_key = await self.s3_service.upload_audio(file_path)
            update_field = "audio_s3_key"
        
        # Update log entry with S3 key
        await self._update_log_entry(task.log_entry_id, {update_field: s3_key})

    async def _execute_transcription(self, task: NetworkTask) -> None:
        """Execute transcription task."""
        payload = task.payload
        audio_file = Path(payload["audio_file"]) if payload.get("audio_file") else None
        s3_key = payload.get("s3_key")
        
        # Determine best file to use
        if not audio_file and s3_key:
            # Need to download from S3 first
            audio_file = await self._download_from_s3(s3_key)
        
        if not audio_file or not audio_file.exists():
            raise TranscriptionError("No valid audio file for transcription")
        
        transcription = await self.openai_service.transcribe_audio(
            audio_file,
            prompt="Captain's log entry from sailing vessel"
        )
        
        # Update log entry and queue next tasks
        await self._update_log_entry(task.log_entry_id, {
            "transcription": transcription,
            "processing_status": ProcessingStatus.VECTORIZING
        })
        
        # Queue embedding and summary generation
        await self.queue_embedding_generation(task.log_entry_id, transcription)
        await self.queue_summary_generation(task.log_entry_id, transcription)

    async def _execute_embedding(self, task: NetworkTask) -> None:
        """Execute embedding generation task."""
        payload = task.payload
        transcription = payload["transcription"]
        
        embedding = await self.openai_service.generate_embedding(transcription)
        
        await self._update_log_entry(task.log_entry_id, {"embedding": embedding})

    async def _execute_summary(self, task: NetworkTask) -> None:
        """Execute summary generation task."""
        payload = task.payload
        transcription = payload["transcription"]
        
        summary = await self.openai_service.generate_summary(
            transcription,
            instructions="Report operational status, environmental conditions, navigational data, and significant events."
        )
        
        await self._update_log_entry(task.log_entry_id, {
            "summary": summary,
            "processing_status": ProcessingStatus.COMPLETED
        })

    async def _download_from_s3(self, s3_key: str) -> Path:
        """Download audio file from S3 to temporary location."""
        import tempfile
        import aiohttp
        
        url = await self.s3_service.get_audio_url(s3_key)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to download audio from S3: {response.status}")
                    
                    async for chunk in response.content.iter_chunked(8192):
                        tmp_file.write(chunk)
        
        return Path(tmp_file.name)

    async def _update_log_entry(self, log_entry_id: str, update_data: Dict[str, Any]) -> None:
        """Update log entry in database."""
        result = await self.db_session.get(LogEntry, log_entry_id)
        if not result:
            raise Exception(f"Log entry not found: {log_entry_id}")
        
        log_entry = result
        
        for field, value in update_data.items():
            if hasattr(log_entry, field):
                setattr(log_entry, field, value)
        
        await self.db_session.commit()

    async def _mark_log_entry_failed(self, log_entry_id: str, error_message: str) -> None:
        """Mark log entry as failed."""
        try:
            await self._update_log_entry(log_entry_id, {
                "processing_status": ProcessingStatus.FAILED,
                "processing_error": error_message
            })
        except Exception as e:
            logger.error(f"Failed to mark log entry as failed: {e}")

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        async with self._queue_lock:
            total_tasks = len(self.task_queue)
            completed_tasks = sum(1 for task in self.task_queue.values() if task.is_completed)
            pending_tasks = sum(1 for task in self.task_queue.values() if task.should_retry())
            failed_tasks = sum(1 for task in self.task_queue.values() 
                             if not task.is_completed and task.retry_count >= task.max_retries)
            
            return {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "failed_tasks": failed_tasks,
                "queue_size": pending_tasks
            }

    async def cleanup_completed_tasks(self, older_than_hours: int = 24) -> None:
        """Clean up completed tasks older than specified hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
        
        async with self._queue_lock:
            tasks_to_remove = [
                task_id for task_id, task in self.task_queue.items()
                if task.is_completed and task.last_attempt and task.last_attempt < cutoff_time
            ]
            
            for task_id in tasks_to_remove:
                del self.task_queue[task_id]
            
            logger.info(f"Cleaned up {len(tasks_to_remove)} completed tasks")


# DBOS workflow integration
@DBOS.workflow()
async def resilient_media_processing_workflow(
    log_entry_id: str,
    media_file_path: str,
    settings_dict: dict
) -> dict:
    """
    DBOS workflow for resilient media processing.
    
    This workflow coordinates the entire media processing pipeline
    with automatic retries and network failure handling.
    """
    try:
        # Initialize processor
        settings = Settings(**settings_dict)
        
        # This would be properly injected in production
        processor = NetworkResilientProcessor(settings, None)
        
        # Start the processor
        await processor.start_processor()
        
        try:
            # Queue initial upload task
            media_path = Path(media_file_path)
            is_video = media_path.suffix.lower() in ['.mp4', '.webm', '.mov', '.avi']
            
            upload_task_id = await processor.queue_s3_upload(
                log_entry_id, 
                media_path, 
                is_video=is_video
            )
            
            # The processor will handle the rest automatically
            # In a real implementation, we'd wait for completion or timeout
            
            return {
                "workflow_id": log_entry_id,
                "status": "queued",
                "upload_task_id": upload_task_id,
                "message": "Media processing queued successfully"
            }
            
        finally:
            await processor.stop_processor()
            
    except Exception as e:
        logger.error(f"Resilient workflow failed: {e}")
        return {
            "workflow_id": log_entry_id,
            "status": "failed",
            "error": str(e)
        }


@DBOS.step()
async def check_network_connectivity() -> bool:
    """DBOS step to check network connectivity."""
    try:
        import aiohttp
        
        # Test basic internet connectivity
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.google.com", timeout=aiohttp.ClientTimeout(total=5)) as response:
                return response.status == 200
    except:
        return False