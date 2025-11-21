"""API endpoints for log management."""
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter, 
    BackgroundTasks, 
    Depends, 
    File, 
    Form,
    HTTPException, 
    Query,
    Request,
    UploadFile,
    status
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.dependencies import get_db_session, get_s3_service, get_openai_service, get_settings
from app.models.log_entry import LogEntry, ProcessingStatus
from app.services.s3 import S3Service
from app.services.openai_client import OpenAIService
from app.services.geocoding import GeocodingService
from app.workflows.audio_processor import AudioProcessingWorkflow
from app.config import Settings

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/logs", tags=["logs"])

# Initialize templates
templates = Jinja2Templates(directory="app/templates")



# Pydantic models for request/response
class LogEntryResponse(BaseModel):
    """Response model for log entry."""
    id: str
    created_at: datetime
    audio_s3_key: str
    transcription: Optional[str] = None
    summary: Optional[str] = None
    processing_status: str
    processing_error: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_country: Optional[str] = None
    body_of_water: Optional[str] = None
    nearest_port: Optional[str] = None

    class Config:
        from_attributes = True


class LogEntryListResponse(BaseModel):
    """Response model for paginated log list."""
    items: List[LogEntryResponse]
    total: int
    page: int
    size: int
    has_next: bool
    has_prev: bool


class LogStatusResponse(BaseModel):
    """Response model for log processing status."""
    id: str
    processing_status: str
    processing_error: Optional[str] = None
    created_at: datetime


class LogAudioResponse(BaseModel):
    """Response model for log audio access."""
    audio_url: str
    expires_at: datetime


class UploadResponse(BaseModel):
    """Response model for file upload."""
    id: str
    audio_s3_key: str
    processing_status: str
    created_at: datetime
    message: str


# File validation
ALLOWED_AUDIO_TYPES = {
    "audio/wav", 
    "audio/wave", 
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/flac",
    "audio/x-flac",
    "audio/webm"
}

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".webm"}


def validate_audio_file(file: UploadFile, max_size: int) -> None:
    """Validate uploaded audio file."""
    # Check file existence
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No file provided"
        )
    
    # Check file size
    if file.size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty file not allowed"
        )
    
    if file.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {max_size_mb:.1f}MB"
        )
    
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid file format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check content type (only if it's not a generic type and extension is invalid)
    if (file.content_type and 
        file.content_type not in ALLOWED_AUDIO_TYPES and
        file.content_type not in ["application/octet-stream"] and  # Allow generic types
        file_ext not in ALLOWED_EXTENSIONS):  # But only if extension is also invalid
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid file format. Expected audio file, got: {file.content_type}"
        )


async def save_uploaded_file(file: UploadFile) -> Path:
    """Save uploaded file to temporary location."""
    # Create temporary file with original extension
    file_ext = Path(file.filename).suffix
    temp_file = tempfile.NamedTemporaryFile(
        delete=False, 
        suffix=file_ext,
        prefix="upload_"
    )
    
    try:
        # Read and save file content
        content = await file.read()
        temp_file.write(content)
        temp_file.flush()
        return Path(temp_file.name)
    finally:
        temp_file.close()


async def start_audio_processing(
    log_entry_id: UUID,
    audio_file_path: Path,
    db_session: AsyncSession,
    settings: Settings,
    s3_service: S3Service,
    openai_service: OpenAIService
) -> None:
    """Start audio processing workflow in background."""
    try:
        logger.info(f"Starting audio processing for log entry: {log_entry_id}")
        
        # Create workflow instance
        workflow = AudioProcessingWorkflow(
            settings=settings,
            db_session=db_session,
            s3_service=s3_service,
            openai_service=openai_service
        )
        
        # Start processing
        await workflow.process_audio(
            log_entry_id=log_entry_id,
            audio_file=audio_file_path
        )
        
        logger.info(f"Audio processing completed for log entry: {log_entry_id}")
        
    except Exception as e:
        logger.error(f"Audio processing failed for {log_entry_id}: {e}")
        # Update log entry with error status
        try:
            result = await db_session.get(LogEntry, log_entry_id)
            if result:
                log_entry = result
                log_entry.processing_status = ProcessingStatus.FAILED
                log_entry.processing_error = str(e)
                await db_session.commit()
        except Exception as update_error:
            logger.error(f"Failed to update error status: {update_error}")
    
    finally:
        # Clean up temporary file
        try:
            audio_file_path.unlink()
        except:
            pass


# API Endpoints

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    location_name: Optional[str] = Form(None),
    db_session: AsyncSession = Depends(get_db_session),
    s3_service: S3Service = Depends(get_s3_service),
    openai_service: OpenAIService = Depends(get_openai_service),
    settings: Settings = Depends(get_settings)
) -> UploadResponse:
    """
    Upload audio file and start processing.
    
    - **file**: Audio file (WAV, MP3, FLAC formats supported)
    - Returns log entry with processing status
    """
    try:
        # Validate file
        validate_audio_file(file, settings.max_audio_file_size)
        
        # Save temporary file
        temp_file_path = await save_uploaded_file(file)
        
        # Enhance location data with geocoding if coordinates are provided
        location_city = None
        location_state = None
        location_country = None
        body_of_water = None
        nearest_port = None
        
        if latitude and longitude:
            try:
                async with GeocodingService() as geocoding_service:
                    location_info = await geocoding_service.reverse_geocode(latitude, longitude)
                    if location_info:
                        location_city = location_info.city
                        location_state = location_info.state
                        location_country = location_info.country
                        body_of_water = location_info.body_of_water
                        nearest_port = location_info.nearest_port
                        logger.info(f"Geocoded location: {location_info.formatted_address}")
            except Exception as geocoding_error:
                logger.warning(f"Geocoding failed: {geocoding_error}, continuing without enhanced location")
        
        # Create log entry (S3 upload will be handled by the workflow)
        log_entry = LogEntry(
            audio_s3_key="",  # Will be set by workflow after upload
            processing_status=ProcessingStatus.PENDING,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            location_city=location_city,
            location_state=location_state,
            location_country=location_country,
            body_of_water=body_of_water,
            nearest_port=nearest_port
        )
        
        db_session.add(log_entry)
        await db_session.commit()
        await db_session.refresh(log_entry)
        
        # Start background processing
        background_tasks.add_task(
            start_audio_processing,
            log_entry.id,
            temp_file_path,
            db_session,
            settings,
            s3_service,
            openai_service
        )
        
        return UploadResponse(
            id=str(log_entry.id),
            audio_s3_key=log_entry.audio_s3_key or "processing",
            processing_status=log_entry.processing_status.value,
            created_at=log_entry.created_at,
            message="File uploaded successfully. Processing started."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload failed. Please try again."
        ) from e


@router.get("")
async def list_log_entries(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[ProcessingStatus] = Query(None, alias="status", description="Filter by processing status"),
    search: Optional[str] = Query(None, description="Search query"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    List log entries with pagination and filtering.
    Returns HTML for HTMX requests, JSON for API requests.
    
    - **page**: Page number (1-based)
    - **size**: Items per page (max 100)
    - **status**: Filter by processing status
    - **search**: Search query
    - **start_date**: Filter logs after this date
    - **end_date**: Filter logs before this date
    """
    try:
        # Check if this is an HTMX request
        is_htmx = request.headers.get("HX-Request") == "true"
        
        # Build query
        query = select(LogEntry).order_by(desc(LogEntry.created_at))
        count_query = select(func.count(LogEntry.id))
        
        # Apply filters
        if status_filter:
            query = query.where(LogEntry.processing_status == status_filter)
            count_query = count_query.where(LogEntry.processing_status == status_filter)
        
        if start_date:
            query = query.where(LogEntry.created_at >= start_date)
            count_query = count_query.where(LogEntry.created_at >= start_date)
        
        if end_date:
            query = query.where(LogEntry.created_at <= end_date)
            count_query = count_query.where(LogEntry.created_at <= end_date)
        
        # Get total count
        total_result = await db_session.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)
        
        # Execute query
        result = await db_session.execute(query)
        log_entries = result.scalars().all()
        
        # For HTMX requests, return HTML
        if is_htmx:
            # Group logs by date
            from collections import defaultdict
            grouped_logs = defaultdict(list)
            
            for entry in log_entries:
                date_key = entry.created_at.date().isoformat()
                grouped_logs[date_key].append(entry)
            
            # Convert to regular dict for template
            grouped_logs = dict(grouped_logs)
            
            # Helper functions for template
            def format_timestamp(dt):
                return dt.strftime("%H:%M")
            
            def format_date(dt):
                return dt.strftime("%Y-%m-%d")
            
            def format_display_date(date_str):
                from datetime import date as dt_date
                date_obj = dt_date.fromisoformat(date_str)
                today = dt_date.today()
                yesterday = today - timedelta(days=1)
                
                if date_obj == today:
                    return "TODAY"
                elif date_obj == yesterday:
                    return "YESTERDAY"
                else:
                    return date_obj.strftime("%A, %B %d, %Y").upper()
            
            def format_location(log):
                from app.services.geocoding import format_location_simple
                
                if log.location_name:
                    # If there's a custom location name, use it but enhance with coordinates if available
                    if log.latitude and log.longitude:
                        return f"{log.latitude:.4f}°, {log.longitude:.4f}° | {log.location_name}"
                    return log.location_name
                elif log.latitude and log.longitude:
                    # Use enhanced formatting if geocoded data is available
                    return format_location_simple(
                        log.latitude, 
                        log.longitude,
                        log.location_city,
                        log.location_state,
                        log.location_country
                    )
                return "Unknown"
            
            def format_status(status):
                return status.value.replace('_', ' ').upper()
            
            def format_uuid_short(uuid_obj):
                return str(uuid_obj)[:8]
            
            # Render template to string instead of using TemplateResponse
            from jinja2 import Environment, FileSystemLoader
            import os
            
            # Get the template directory path
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template("fragments/log_entries.html")
            
            html_content = template.render(
                request=request,
                logs=log_entries,
                grouped_logs=grouped_logs,
                page=page,
                has_next=offset + size < total,
                has_prev=page > 1,
                status=status_filter.value if status_filter else None,
                search=search,
                format_timestamp=format_timestamp,
                format_date=format_date,
                format_display_date=format_display_date,
                format_location=format_location,
                format_status=format_status,
                format_uuid_short=format_uuid_short
            )
            
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html_content)
        
        # For JSON API requests, return JSON
        items = [
            LogEntryResponse(
                id=str(entry.id),
                created_at=entry.created_at,
                audio_s3_key=entry.audio_s3_key,
                transcription=entry.transcription,
                summary=entry.summary,
                processing_status=entry.processing_status.value,
                processing_error=entry.processing_error,
                latitude=entry.latitude,
                longitude=entry.longitude,
                location_name=entry.location_name,
                location_city=entry.location_city,
                location_state=entry.location_state,
                location_country=entry.location_country,
                body_of_water=entry.body_of_water,
                nearest_port=entry.nearest_port
            )
            for entry in log_entries
        ]
        
        return LogEntryListResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            has_next=offset + size < total,
            has_prev=page > 1
        )
        
    except Exception as e:
        logger.error(f"Failed to list log entries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve log entries"
        ) from e


@router.get("/{log_id}", response_model=LogEntryResponse)
async def get_log_entry(
    log_id: UUID,
    db_session: AsyncSession = Depends(get_db_session)
) -> LogEntryResponse:
    """
    Get detailed information about a specific log entry.
    
    - **log_id**: UUID of the log entry
    """
    try:
        result = await db_session.get(LogEntry, log_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Log entry not found"
            )
        
        log_entry = result
        
        return LogEntryResponse(
            id=str(log_entry.id),
            created_at=log_entry.created_at,
            audio_s3_key=log_entry.audio_s3_key,
            transcription=log_entry.transcription,
            summary=log_entry.summary,
            processing_status=log_entry.processing_status.value,
            processing_error=log_entry.processing_error,
            latitude=log_entry.latitude,
            longitude=log_entry.longitude,
            location_name=log_entry.location_name,
            location_city=log_entry.location_city,
            location_state=log_entry.location_state,
            location_country=log_entry.location_country,
            body_of_water=log_entry.body_of_water,
            nearest_port=log_entry.nearest_port
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get log entry {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve log entry"
        ) from e


@router.get("/{log_id}/status", response_model=LogStatusResponse)
async def get_log_status(
    log_id: UUID,
    db_session: AsyncSession = Depends(get_db_session)
) -> LogStatusResponse:
    """
    Get processing status of a log entry.
    
    - **log_id**: UUID of the log entry
    """
    try:
        result = await db_session.get(LogEntry, log_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Log entry not found"
            )
        
        log_entry = result
        
        return LogStatusResponse(
            id=str(log_entry.id),
            processing_status=log_entry.processing_status.value,
            processing_error=log_entry.processing_error,
            created_at=log_entry.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get log status {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve log status"
        ) from e


@router.get("/{log_id}/audio", response_model=LogAudioResponse)
async def get_log_audio(
    log_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    s3_service: S3Service = Depends(get_s3_service)
) -> LogAudioResponse:
    """
    Get presigned URL for log audio file.
    
    - **log_id**: UUID of the log entry
    """
    try:
        result = await db_session.get(LogEntry, log_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Log entry not found"
            )
        
        log_entry = result
        
        # Generate presigned URL
        try:
            audio_url = await s3_service.get_audio_url(log_entry.audio_s3_key)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found"
            )
        except Exception as s3_error:
            logger.error(f"S3 URL generation failed: {s3_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Audio access failed"
            )
        
        # Calculate expiration (presigned URLs typically expire in 1 hour)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        return LogAudioResponse(
            audio_url=audio_url,
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get log audio {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve log audio"
        ) from e


@router.delete("/{log_id}")
async def delete_log_entry(
    log_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),
    s3_service: S3Service = Depends(get_s3_service)
) -> dict:
    """
    Delete a log entry and its associated audio file.
    
    - **log_id**: UUID of the log entry to delete
    """
    logger.info(f"Starting delete operation for log entry: {log_id}")
    try:
        # Get the log entry
        logger.info(f"About to query database for log entry: {log_id}")
        result = await db_session.get(LogEntry, log_id)
        logger.info(f"Database query completed, result: {result}")
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Log entry not found"
            )
        
        log_entry = result
        audio_s3_key = log_entry.audio_s3_key  # Store for S3 cleanup after DB deletion
        
        # Delete from database first
        await db_session.delete(log_entry)
        await db_session.commit()
        
        logger.info(f"Successfully deleted log entry from database: {log_id}")
        
        # Delete from S3 after successful DB deletion
        if audio_s3_key:
            try:
                await s3_service.delete_audio(audio_s3_key)
                logger.info(f"Deleted audio file from S3: {audio_s3_key}")
            except Exception as s3_error:
                logger.warning(f"Failed to delete S3 file {audio_s3_key}: {s3_error}")
                # S3 deletion failure doesn't affect the API response since DB deletion succeeded
        
        return {"message": "Log entry deleted successfully", "id": str(log_id)}
        
    except HTTPException:
        logger.info(f"HTTPException caught for {log_id}, re-raising")
        raise
    except Exception as e:
        # Rollback the transaction if it's still active
        try:
            await db_session.rollback()
        except Exception as rollback_error:
            logger.warning(f"Rollback failed: {rollback_error}")
        logger.error(f"Failed to delete log entry {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete log entry"
        ) from e