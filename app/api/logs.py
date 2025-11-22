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
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.dependencies import get_db_session, get_s3_service, get_openai_service, get_settings, get_media_storage_service, get_current_user, verify_log_ownership
from app.models.log_entry import LogEntry, ProcessingStatus, MediaType, LogType
from app.models.user import User
from app.services.s3 import S3Service
from app.services.media_storage import MediaStorageService
from app.services.openai_client import OpenAIService
from app.services.geocoding import GeocodingService
from app.services.weather_service import weather_service
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
    media_type: str
    is_video_source: bool
    log_type: str
    video_s3_key: Optional[str] = None
    video_local_path: Optional[str] = None
    audio_s3_key: Optional[str] = None
    audio_local_path: Optional[str] = None
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
    
    # Weather fields
    weather_air_temp_f: Optional[float] = None
    weather_water_temp_f: Optional[float] = None
    weather_wind_speed_kts: Optional[float] = None
    weather_wind_direction_deg: Optional[float] = None
    weather_wind_gust_kts: Optional[float] = None
    weather_wave_height_ft: Optional[float] = None
    weather_wave_period_sec: Optional[float] = None
    weather_barometric_pressure_mb: Optional[float] = None
    weather_visibility_nm: Optional[float] = None
    weather_conditions: Optional[str] = None
    weather_forecast: Optional[str] = None
    weather_captured_at: Optional[datetime] = None
    weather_relative_humidity_pct: Optional[float] = None
    weather_dew_point_f: Optional[float] = None
    weather_precipitation_probability_pct: Optional[float] = None
    weather_precipitation_amount_in: Optional[float] = None

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
    media_type: str
    is_video_source: bool
    video_s3_key: Optional[str] = None
    video_local_path: Optional[str] = None
    audio_s3_key: Optional[str] = None
    audio_local_path: Optional[str] = None
    processing_status: str
    created_at: datetime
    message: str


class LogTypeUpdateRequest(BaseModel):
    """Request model for updating log type."""
    log_type: str = Field(..., pattern=r"^(PERSONAL|SHIP)$")


class LogTypeUpdateResponse(BaseModel):
    """Response model for log type update."""
    id: str
    log_type: str
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

ALLOWED_VIDEO_TYPES = {
    "video/webm",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo"
}

ALLOWED_MEDIA_TYPES = ALLOWED_AUDIO_TYPES | ALLOWED_VIDEO_TYPES

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".webm", ".mp4", ".mov", ".avi"}


def validate_media_file(file: UploadFile, max_size: int, media_type: str = "audio") -> None:
    """Validate uploaded media file (audio or video)."""
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
    
    # Use larger limit for video files (10x audio limit)
    max_file_size = max_size * 10 if media_type == "video" else max_size
    
    if file.size > max_file_size:
        max_size_mb = max_file_size / (1024 * 1024)
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
    
    # Validate content type based on media type
    allowed_types = ALLOWED_VIDEO_TYPES if media_type == "video" else ALLOWED_AUDIO_TYPES
    
    # Check content type (only if it's not a generic type and extension is invalid)
    if (file.content_type and 
        file.content_type not in allowed_types and
        file.content_type not in ALLOWED_MEDIA_TYPES and
        file.content_type not in ["application/octet-stream"] and  # Allow generic types
        file_ext not in ALLOWED_EXTENSIONS):  # But only if extension is also invalid
        expected_type = "video" if media_type == "video" else "audio"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid file format. Expected {expected_type} file, got: {file.content_type}"
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


async def start_media_processing(
    log_entry_id: UUID,
    media_file_path: Path,
    db_session: AsyncSession,
    settings: Settings,
    media_storage: MediaStorageService,
    openai_service: OpenAIService,
    use_resilient_processing: bool = True
) -> None:
    """Start media processing workflow in background (supports audio and video)."""
    try:
        logger.info(f"Starting media processing for log entry: {log_entry_id}")
        
        # Create workflow instance with resilient processing option
        workflow = AudioProcessingWorkflow(
            settings=settings,
            db_session=db_session,
            media_storage=media_storage,
            openai_service=openai_service,
            use_resilient_processor=use_resilient_processing
        )
        
        # Use resilient processing if enabled, otherwise fall back to regular processing
        if use_resilient_processing:
            logger.info(f"Using network-resilient processing for: {log_entry_id}")
            result = await workflow.process_media_resilient(
                log_entry_id=log_entry_id,
                media_file=media_file_path
            )
            logger.info(f"Media processing queued successfully: {result}")
        else:
            logger.info(f"Using regular processing for: {log_entry_id}")
            await workflow.process_media(
                log_entry_id=log_entry_id,
                media_file=media_file_path
            )
            logger.info(f"Media processing completed for log entry: {log_entry_id}")
        
    except Exception as e:
        logger.error(f"Media processing failed for {log_entry_id}: {e}")
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
        # Clean up temporary file only if not using resilient processing
        # (resilient processing may need the file later)
        if not use_resilient_processing:
            try:
                media_file_path.unlink()
            except:
                pass


# API Endpoints

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_media_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    media_type: str = Form("audio"),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    location_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    media_storage: MediaStorageService = Depends(get_media_storage_service),
    openai_service: OpenAIService = Depends(get_openai_service),
    settings: Settings = Depends(get_settings)
) -> UploadResponse:
    """
    Upload media file (audio or video) and start processing.
    
    - **file**: Media file (WAV, MP3, FLAC, MP4, WEBM formats supported)
    - **media_type**: Type of media ("audio" or "video")
    - Returns log entry with processing status
    """
    try:
        # Validate file
        validate_media_file(file, settings.max_audio_file_size, media_type)
        
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
        
        # Capture weather conditions if coordinates are provided
        weather_data = {}
        if latitude and longitude:
            try:
                weather_conditions = await weather_service.get_marine_conditions(latitude, longitude)
                if weather_conditions:
                    # Convert timezone-aware datetime to naive for database storage
                    captured_at = weather_conditions.get('captured_at')
                    if captured_at and hasattr(captured_at, 'replace'):
                        captured_at = captured_at.replace(tzinfo=None)
                    
                    weather_data = {
                        'weather_air_temp_f': weather_conditions.get('air_temp_f'),
                        'weather_water_temp_f': weather_conditions.get('water_temp_f'),
                        'weather_wind_speed_kts': weather_conditions.get('wind_speed_kts'),
                        'weather_wind_direction_deg': weather_conditions.get('wind_direction_deg'),
                        'weather_wind_gust_kts': weather_conditions.get('wind_gust_kts'),
                        'weather_wave_height_ft': weather_conditions.get('wave_height_ft'),
                        'weather_wave_period_sec': weather_conditions.get('wave_period_sec'),
                        'weather_barometric_pressure_mb': weather_conditions.get('barometric_pressure_mb'),
                        'weather_visibility_nm': weather_conditions.get('visibility_nm'),
                        'weather_conditions': weather_conditions.get('conditions'),
                        'weather_forecast': weather_conditions.get('forecast'),
                        'weather_captured_at': captured_at,
                        'weather_relative_humidity_pct': weather_conditions.get('relative_humidity_pct'),
                        'weather_dew_point_f': weather_conditions.get('dew_point_f'),
                        'weather_precipitation_probability_pct': weather_conditions.get('precipitation_probability_pct'),
                        'weather_precipitation_amount_in': weather_conditions.get('precipitation_amount_in')
                    }
                    logger.info(f"Captured weather data: {len([k for k, v in weather_data.items() if v is not None])} fields")
            except Exception as weather_error:
                logger.warning(f"Weather capture failed: {weather_error}, continuing without weather data")
        
        # Determine media type and video source flag
        file_ext = Path(file.filename).suffix.lower()
        is_video = file_ext in {'.mp4', '.webm', '.mov', '.avi'} or media_type == "video"
        
        # Create log entry (media storage will be handled by the workflow)
        log_entry = LogEntry(
            user_id=current_user.id,
            media_type=MediaType.VIDEO if is_video else MediaType.AUDIO,
            original_filename=file.filename,
            is_video_source=is_video,
            audio_s3_key=None,  # Will be set by workflow after storage
            audio_local_path=None,  # Will be set by workflow if using local storage
            processing_status=ProcessingStatus.PENDING,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            location_city=location_city,
            location_state=location_state,
            location_country=location_country,
            body_of_water=body_of_water,
            nearest_port=nearest_port,
            **weather_data  # Include weather data fields
        )
        
        db_session.add(log_entry)
        await db_session.commit()
        await db_session.refresh(log_entry)
        
        # Start background processing
        background_tasks.add_task(
            start_media_processing,
            log_entry.id,
            temp_file_path,
            db_session,
            settings,
            media_storage,
            openai_service
        )
        
        return UploadResponse(
            id=str(log_entry.id),
            media_type=log_entry.media_type.value,
            is_video_source=log_entry.is_video_source,
            video_s3_key=log_entry.video_s3_key,
            video_local_path=log_entry.video_local_path,
            audio_s3_key=log_entry.audio_s3_key,
            audio_local_path=log_entry.audio_local_path,
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
    log_type_filter: Optional[LogType] = Query(None, alias="log_type", description="Filter by log type"),
    search: Optional[str] = Query(None, description="Search query"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    List log entries with pagination and filtering.
    Returns HTML for HTMX requests, JSON for API requests.
    
    - **page**: Page number (1-based)
    - **size**: Items per page (max 100)
    - **status**: Filter by processing status
    - **log_type**: Filter by log type (personal/ship)
    - **search**: Search query
    - **start_date**: Filter logs after this date
    - **end_date**: Filter logs before this date
    """
    try:
        # Check if this is an HTMX request
        is_htmx = request.headers.get("HX-Request") == "true"

        # Build query - filter PERSONAL logs by current user, but show all SHIP logs
        from sqlalchemy import or_
        user_filter = or_(
            LogEntry.log_type == LogType.SHIP,  # All users can see ship's logs
            LogEntry.user_id == current_user.id  # Only owner can see personal logs
        )
        query = select(LogEntry).where(user_filter).order_by(desc(LogEntry.created_at))
        count_query = select(func.count(LogEntry.id)).where(user_filter)

        # Apply filters
        if status_filter:
            query = query.where(LogEntry.processing_status == status_filter)
            count_query = count_query.where(LogEntry.processing_status == status_filter)
        
        if log_type_filter:
            query = query.where(LogEntry.log_type == log_type_filter)
            count_query = count_query.where(LogEntry.log_type == log_type_filter)
        
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
                log_type=log_type_filter.value if log_type_filter else None,
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
                media_type=entry.media_type.value,
                is_video_source=entry.is_video_source,
                log_type=entry.log_type.value,
                video_s3_key=entry.video_s3_key,
                video_local_path=entry.video_local_path,
                audio_s3_key=entry.audio_s3_key,
                audio_local_path=entry.audio_local_path,
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
                nearest_port=entry.nearest_port,
                weather_air_temp_f=entry.weather_air_temp_f,
                weather_water_temp_f=entry.weather_water_temp_f,
                weather_wind_speed_kts=entry.weather_wind_speed_kts,
                weather_wind_direction_deg=entry.weather_wind_direction_deg,
                weather_wind_gust_kts=entry.weather_wind_gust_kts,
                weather_wave_height_ft=entry.weather_wave_height_ft,
                weather_wave_period_sec=entry.weather_wave_period_sec,
                weather_barometric_pressure_mb=entry.weather_barometric_pressure_mb,
                weather_visibility_nm=entry.weather_visibility_nm,
                weather_conditions=entry.weather_conditions,
                weather_forecast=entry.weather_forecast,
                weather_captured_at=entry.weather_captured_at
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


@router.get("/search")
async def search_logs(
    request: Request,
    query: str = Query(..., description="Search query text"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    openai_service: OpenAIService = Depends(get_openai_service)
):
    """
    Perform vector similarity search on log entries.

    - **query**: Search text to vectorize and search
    - **limit**: Maximum number of results to return (default 10, max 50)
    """
    try:
        # Check if this is an HTMX request
        is_htmx = request.headers.get("HX-Request") == "true"

        # Generate embedding for the search query
        try:
            query_embedding = await openai_service.generate_embedding(query)
        except Exception as embedding_error:
            logger.error(f"Failed to generate embedding for search query: {embedding_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process search query"
            )

        # Perform vector similarity search using pgvector's cosine distance operator
        # The <=> operator computes cosine distance (lower is more similar)
        # We order by distance ascending to get the most similar results first
        # Filter PERSONAL logs by current user, but show all SHIP logs
        from sqlalchemy import text, or_

        user_filter = or_(
            LogEntry.log_type == LogType.SHIP,  # All users can see ship's logs
            LogEntry.user_id == current_user.id  # Only owner can see personal logs
        )
        similarity_query = select(LogEntry).where(
            user_filter,
            LogEntry.embedding.isnot(None)
        ).order_by(
            LogEntry.embedding.cosine_distance(query_embedding)
        ).limit(limit)

        result = await db_session.execute(similarity_query)
        log_entries = result.scalars().all()

        # For HTMX requests, return HTML
        if is_htmx:
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
                    if log.latitude and log.longitude:
                        return f"{log.latitude:.4f}°, {log.longitude:.4f}° | {log.location_name}"
                    return log.location_name
                elif log.latitude and log.longitude:
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

            # Group logs by date
            from collections import defaultdict
            grouped_logs = defaultdict(list)

            for entry in log_entries:
                date_key = entry.created_at.date().isoformat()
                grouped_logs[date_key].append(entry)

            grouped_logs = dict(grouped_logs)

            # Render template
            from jinja2 import Environment, FileSystemLoader
            import os

            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template("fragments/search_results.html")

            html_content = template.render(
                request=request,
                logs=log_entries,
                grouped_logs=grouped_logs,
                query=query,
                format_timestamp=format_timestamp,
                format_date=format_date,
                format_display_date=format_display_date,
                format_location=format_location,
                format_status=format_status,
                format_uuid_short=format_uuid_short
            )

            return HTMLResponse(content=html_content)

        # For JSON API requests, return JSON
        items = [
            LogEntryResponse(
                id=str(entry.id),
                created_at=entry.created_at,
                media_type=entry.media_type.value,
                is_video_source=entry.is_video_source,
                log_type=entry.log_type.value,
                video_s3_key=entry.video_s3_key,
                video_local_path=entry.video_local_path,
                audio_s3_key=entry.audio_s3_key,
                audio_local_path=entry.audio_local_path,
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
                nearest_port=entry.nearest_port,
                weather_air_temp_f=entry.weather_air_temp_f,
                weather_water_temp_f=entry.weather_water_temp_f,
                weather_wind_speed_kts=entry.weather_wind_speed_kts,
                weather_wind_direction_deg=entry.weather_wind_direction_deg,
                weather_wind_gust_kts=entry.weather_wind_gust_kts,
                weather_wave_height_ft=entry.weather_wave_height_ft,
                weather_wave_period_sec=entry.weather_wave_period_sec,
                weather_barometric_pressure_mb=entry.weather_barometric_pressure_mb,
                weather_visibility_nm=entry.weather_visibility_nm,
                weather_conditions=entry.weather_conditions,
                weather_forecast=entry.weather_forecast,
                weather_captured_at=entry.weather_captured_at
            )
            for entry in log_entries
        ]

        return {
            "query": query,
            "results": items,
            "count": len(items)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed"
        ) from e


@router.get("/{log_id}", response_model=LogEntryResponse)
async def get_log_entry(
    log_id: UUID,
    current_user: User = Depends(get_current_user),
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

        # Verify ownership for PERSONAL logs only (SHIP logs are accessible to all)
        if log_entry.log_type == LogType.PERSONAL:
            verify_log_ownership(log_entry, current_user)

        return LogEntryResponse(
            id=str(log_entry.id),
            created_at=log_entry.created_at,
            media_type=log_entry.media_type.value,
            is_video_source=log_entry.is_video_source,
            log_type=log_entry.log_type.value,
            video_s3_key=log_entry.video_s3_key,
            video_local_path=log_entry.video_local_path,
            audio_s3_key=log_entry.audio_s3_key,
            audio_local_path=log_entry.audio_local_path,
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
            nearest_port=log_entry.nearest_port,
            weather_air_temp_f=log_entry.weather_air_temp_f,
            weather_water_temp_f=log_entry.weather_water_temp_f,
            weather_wind_speed_kts=log_entry.weather_wind_speed_kts,
            weather_wind_direction_deg=log_entry.weather_wind_direction_deg,
            weather_wind_gust_kts=log_entry.weather_wind_gust_kts,
            weather_wave_height_ft=log_entry.weather_wave_height_ft,
            weather_wave_period_sec=log_entry.weather_wave_period_sec,
            weather_barometric_pressure_mb=log_entry.weather_barometric_pressure_mb,
            weather_visibility_nm=log_entry.weather_visibility_nm,
            weather_conditions=log_entry.weather_conditions,
            weather_forecast=log_entry.weather_forecast,
            weather_captured_at=log_entry.weather_captured_at
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
    current_user: User = Depends(get_current_user),
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

        # Verify ownership for PERSONAL logs only (SHIP logs are accessible to all)
        if log_entry.log_type == LogType.PERSONAL:
            verify_log_ownership(log_entry, current_user)

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
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    media_storage: MediaStorageService = Depends(get_media_storage_service)
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

        # Verify ownership for PERSONAL logs only (SHIP logs are accessible to all)
        if log_entry.log_type == LogType.PERSONAL:
            verify_log_ownership(log_entry, current_user)

        # Generate audio URL based on storage mode
        try:
            audio_url = await media_storage.get_audio_url(
                s3_key=log_entry.audio_s3_key,
                local_path=log_entry.audio_local_path
            )
        except Exception as storage_error:
            logger.error(f"Audio URL generation failed: {storage_error}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found"
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


@router.patch("/{log_id}/log-type", response_model=LogTypeUpdateResponse)
async def update_log_type(
    log_id: UUID,
    update_request: LogTypeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session)
) -> LogTypeUpdateResponse:
    """
    Update the log type of a log entry.

    - **log_id**: UUID of the log entry to update
    - **log_type**: New log type ("PERSONAL" or "SHIP")
    """
    try:
        # Get the log entry
        result = await db_session.get(LogEntry, log_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Log entry not found"
            )

        log_entry = result

        # Verify ownership - only owner can modify logs
        verify_log_ownership(log_entry, current_user)

        # Convert string to enum
        try:
            new_log_type = LogType.PERSONAL if update_request.log_type == "PERSONAL" else LogType.SHIP
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid log type. Must be 'PERSONAL' or 'SHIP'"
            )
        
        # Update log type
        old_log_type = log_entry.log_type
        log_entry.log_type = new_log_type
        
        # Commit changes
        await db_session.commit()
        await db_session.refresh(log_entry)
        
        logger.info(f"Updated log type for {log_id}: {old_log_type.value} -> {new_log_type.value}")
        
        return LogTypeUpdateResponse(
            id=str(log_entry.id),
            log_type=new_log_type.value.upper(),
            message=f"Log type updated to {new_log_type.value.title()} Log"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Rollback the transaction if it's still active
        try:
            await db_session.rollback()
        except Exception as rollback_error:
            logger.warning(f"Rollback failed: {rollback_error}")
        logger.error(f"Failed to update log type for {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update log type"
        ) from e


@router.post("/{log_id}/retry")
async def retry_log_processing(
    log_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    media_storage: MediaStorageService = Depends(get_media_storage_service),
    openai_service: OpenAIService = Depends(get_openai_service),
    settings: Settings = Depends(get_settings)
) -> dict:
    """
    Retry processing for a failed or stuck log entry.

    This endpoint will re-run the transcription workflow for log entries that are:
    - In FAILED status
    - Stuck in TRANSCRIBING, VECTORIZING, or SUMMARIZING status

    - **log_id**: UUID of the log entry to retry
    """
    try:
        # Get the log entry
        result = await db_session.get(LogEntry, log_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Log entry not found"
            )

        log_entry = result

        # Verify ownership - only owner can retry logs
        verify_log_ownership(log_entry, current_user)

        # Check if the log entry needs retry
        retryable_statuses = {
            ProcessingStatus.FAILED,
            ProcessingStatus.TRANSCRIBING,
            ProcessingStatus.VECTORIZING,
            ProcessingStatus.SUMMARIZING
        }

        if log_entry.processing_status == ProcessingStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Log entry is already completed and does not need retry"
            )

        if log_entry.processing_status not in retryable_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Log entry in {log_entry.processing_status.value} status cannot be retried"
            )

        # Check if we have the necessary media files
        if not log_entry.audio_s3_key and not log_entry.audio_local_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No audio file found for this log entry"
            )

        # Reset status to PENDING and clear error
        log_entry.processing_status = ProcessingStatus.PENDING
        log_entry.processing_error = None
        await db_session.commit()
        await db_session.refresh(log_entry)

        # Get the audio file path
        # Try local path first, then download from S3 if needed
        media_file_path = None
        temp_file_created = False

        if log_entry.audio_local_path and Path(log_entry.audio_local_path).exists():
            media_file_path = Path(log_entry.audio_local_path)
        elif log_entry.audio_s3_key:
            # Download from S3 to temporary file
            try:
                s3_service = S3Service(settings)
                audio_url = await s3_service.get_audio_url(log_entry.audio_s3_key)

                # Download to temp file
                import aiohttp
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav', prefix='retry_')
                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_url) as response:
                        if response.status != 200:
                            raise Exception(f"Failed to download audio from S3: {response.status}")

                        async for chunk in response.content.iter_chunked(8192):
                            temp_file.write(chunk)

                temp_file.close()
                media_file_path = Path(temp_file.name)
                temp_file_created = True

            except Exception as download_error:
                logger.error(f"Failed to download audio for retry: {download_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve audio file for retry"
                )

        if not media_file_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not locate audio file for retry"
            )

        # Start background processing
        background_tasks.add_task(
            start_media_processing,
            log_entry.id,
            media_file_path,
            db_session,
            settings,
            media_storage,
            openai_service,
            use_resilient_processing=settings.enable_resilient_processing
        )

        logger.info(f"Retry processing queued for log entry: {log_id}")

        return {
            "message": "Processing retry started successfully",
            "id": str(log_id),
            "status": log_entry.processing_status.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry log processing {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry log processing"
        ) from e


@router.delete("/{log_id}")
async def delete_log_entry(
    log_id: UUID,
    current_user: User = Depends(get_current_user),
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

        # Verify ownership - only owner can delete logs
        verify_log_ownership(log_entry, current_user)

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


# Media serving endpoint for local files
@router.get("/media/local/{filename}")
async def serve_local_media(
    filename: str,
    settings: Settings = Depends(get_settings)
):
    """Serve local media files when using local storage mode."""
    from app.config import MediaStorageMode

    if settings.media_storage_mode != MediaStorageMode.LOCAL_WITH_S3:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local media serving not enabled"
        )

    if not settings.local_media_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local media path not configured"
        )

    # Security check: ensure filename doesn't contain path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )

    # Find the file in the local media directory
    media_path = Path(settings.local_media_path)

    # Search for the file in subdirectories (date-based structure)
    for file_path in media_path.rglob(filename):
        if file_path.is_file():
            return FileResponse(
                path=str(file_path),
                media_type="audio/mpeg"  # Default to audio type
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Media file not found"
    )