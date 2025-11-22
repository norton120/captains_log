"""API endpoints for settings management."""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.dependencies import get_db_session
from app.models.settings import UserPreferences, Setting, MediaStorageMode

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/settings", tags=["settings"])

# Initialize templates
templates = Jinja2Templates(directory="app/templates")


# Pydantic models for request/response
class UserPreferencesResponse(BaseModel):
    """Response model for user preferences."""

    id: str
    app_name: str
    vessel_name: str
    vessel_designation: str
    openai_model_whisper: str
    openai_model_embedding: str
    openai_model_chat: str
    media_storage_mode: str
    local_media_path: Optional[str] = None
    max_audio_file_size: int
    max_video_file_size: int
    allowed_audio_formats: List[str]
    allowed_video_formats: List[str]
    default_page_size: int
    max_page_size: int
    enable_resilient_processing: bool
    max_network_retries: int
    network_retry_base_delay: int
    network_retry_max_delay: int
    # AWS/S3 settings
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    s3_bucket_name: Optional[str] = None
    s3_base_url: Optional[str] = None
    s3_audio_prefix: str
    s3_video_prefix: str
    s3_presigned_url_expiry: int
    # Authentication settings
    allow_new_user_registration: bool
    secret_key: Optional[str] = None
    session_cookie_name: str
    session_max_age: int
    # OAuth settings
    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    facebook_oauth_client_id: Optional[str] = None
    facebook_oauth_client_secret: Optional[str] = None
    github_oauth_client_id: Optional[str] = None
    github_oauth_client_secret: Optional[str] = None

    class Config:
        from_attributes = True


class UserPreferencesUpdateRequest(BaseModel):
    """Request model for updating user preferences."""

    app_name: Optional[str] = Field(None, min_length=1, max_length=255)
    vessel_name: Optional[str] = Field(None, min_length=1, max_length=255)
    vessel_designation: Optional[str] = Field(None, min_length=1, max_length=255)
    openai_model_whisper: Optional[str] = Field(None, min_length=1, max_length=100)
    openai_model_embedding: Optional[str] = Field(None, min_length=1, max_length=100)
    openai_model_chat: Optional[str] = Field(None, min_length=1, max_length=100)
    media_storage_mode: Optional[MediaStorageMode] = None
    local_media_path: Optional[str] = Field(None, max_length=500)
    max_audio_file_size: Optional[int] = Field(None, gt=0)
    max_video_file_size: Optional[int] = Field(None, gt=0)
    allowed_audio_formats: Optional[List[str]] = None
    allowed_video_formats: Optional[List[str]] = None
    default_page_size: Optional[int] = Field(None, gt=0, le=100)
    max_page_size: Optional[int] = Field(None, gt=0, le=1000)
    enable_resilient_processing: Optional[bool] = None
    max_network_retries: Optional[int] = Field(None, ge=1, le=100)
    network_retry_base_delay: Optional[int] = Field(None, ge=1, le=3600)
    network_retry_max_delay: Optional[int] = Field(None, ge=1, le=86400)
    # AWS/S3 settings
    aws_access_key_id: Optional[str] = Field(None, max_length=255)
    aws_secret_access_key: Optional[str] = Field(None, max_length=255)
    aws_region: Optional[str] = Field(None, max_length=50)
    s3_bucket_name: Optional[str] = Field(None, max_length=255)
    s3_base_url: Optional[str] = Field(None, max_length=500)
    s3_audio_prefix: Optional[str] = Field(None, min_length=1, max_length=100)
    s3_video_prefix: Optional[str] = Field(None, min_length=1, max_length=100)
    s3_presigned_url_expiry: Optional[int] = Field(None, gt=0, le=604800)
    # Authentication settings
    allow_new_user_registration: Optional[bool] = None
    secret_key: Optional[str] = Field(None, max_length=255)
    session_cookie_name: Optional[str] = Field(None, max_length=100)
    session_max_age: Optional[int] = Field(None, gt=0)
    # OAuth settings
    google_oauth_client_id: Optional[str] = Field(None, max_length=255)
    google_oauth_client_secret: Optional[str] = Field(None, max_length=255)
    facebook_oauth_client_id: Optional[str] = Field(None, max_length=255)
    facebook_oauth_client_secret: Optional[str] = Field(None, max_length=255)
    github_oauth_client_id: Optional[str] = Field(None, max_length=255)
    github_oauth_client_secret: Optional[str] = Field(None, max_length=255)


class SettingResponse(BaseModel):
    """Response model for individual settings."""

    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    setting_type: str

    class Config:
        from_attributes = True


class SettingUpdateRequest(BaseModel):
    """Request model for updating a setting."""

    value: Optional[str] = None
    description: Optional[str] = None


async def get_or_create_user_preferences(db_session: AsyncSession) -> UserPreferences:
    """Get existing user preferences or create default ones."""
    # Check if preferences exist
    query = select(UserPreferences).limit(1)
    result = await db_session.execute(query)
    preferences = result.scalar_one_or_none()

    if not preferences:
        # Create default preferences
        preferences = UserPreferences()
        db_session.add(preferences)
        await db_session.commit()
        await db_session.refresh(preferences)

    return preferences


# API Endpoints


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(db_session: AsyncSession = Depends(get_db_session)) -> UserPreferencesResponse:
    """
    Get current user preferences.
    """
    try:
        preferences = await get_or_create_user_preferences(db_session)

        return UserPreferencesResponse(
            id=str(preferences.id),
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
            openai_model_whisper=preferences.openai_model_whisper,
            openai_model_embedding=preferences.openai_model_embedding,
            openai_model_chat=preferences.openai_model_chat,
            media_storage_mode=preferences.media_storage_mode.value,
            local_media_path=preferences.local_media_path,
            max_audio_file_size=preferences.max_audio_file_size,
            max_video_file_size=preferences.max_video_file_size,
            allowed_audio_formats=preferences.allowed_audio_formats,
            allowed_video_formats=preferences.allowed_video_formats,
            default_page_size=preferences.default_page_size,
            max_page_size=preferences.max_page_size,
            enable_resilient_processing=preferences.enable_resilient_processing,
            max_network_retries=preferences.max_network_retries,
            network_retry_base_delay=preferences.network_retry_base_delay,
            network_retry_max_delay=preferences.network_retry_max_delay,
            # AWS/S3 settings
            aws_access_key_id=preferences.aws_access_key_id,
            aws_secret_access_key=preferences.aws_secret_access_key,
            aws_region=preferences.aws_region,
            s3_bucket_name=preferences.s3_bucket_name,
            s3_base_url=preferences.s3_base_url,
            s3_audio_prefix=preferences.s3_audio_prefix,
            s3_video_prefix=preferences.s3_video_prefix,
            s3_presigned_url_expiry=preferences.s3_presigned_url_expiry,
        )

    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve preferences"
        ) from e


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    update_request: UserPreferencesUpdateRequest, db_session: AsyncSession = Depends(get_db_session)
) -> UserPreferencesResponse:
    """
    Update user preferences.

    Only provided fields will be updated. Omitted fields will keep their current values.
    """
    try:
        preferences = await get_or_create_user_preferences(db_session)

        # Update only provided fields
        update_data = update_request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(preferences, field):
                setattr(preferences, field, value)

        await db_session.commit()
        await db_session.refresh(preferences)

        logger.info(f"Updated user preferences: {list(update_data.keys())}")

        return UserPreferencesResponse(
            id=str(preferences.id),
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
            openai_model_whisper=preferences.openai_model_whisper,
            openai_model_embedding=preferences.openai_model_embedding,
            openai_model_chat=preferences.openai_model_chat,
            media_storage_mode=preferences.media_storage_mode.value,
            local_media_path=preferences.local_media_path,
            max_audio_file_size=preferences.max_audio_file_size,
            max_video_file_size=preferences.max_video_file_size,
            allowed_audio_formats=preferences.allowed_audio_formats,
            allowed_video_formats=preferences.allowed_video_formats,
            default_page_size=preferences.default_page_size,
            max_page_size=preferences.max_page_size,
            enable_resilient_processing=preferences.enable_resilient_processing,
            max_network_retries=preferences.max_network_retries,
            network_retry_base_delay=preferences.network_retry_base_delay,
            network_retry_max_delay=preferences.network_retry_max_delay,
            # AWS/S3 settings
            aws_access_key_id=preferences.aws_access_key_id,
            aws_secret_access_key=preferences.aws_secret_access_key,
            aws_region=preferences.aws_region,
            s3_bucket_name=preferences.s3_bucket_name,
            s3_base_url=preferences.s3_base_url,
            s3_audio_prefix=preferences.s3_audio_prefix,
            s3_video_prefix=preferences.s3_video_prefix,
            s3_presigned_url_expiry=preferences.s3_presigned_url_expiry,
        )

    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        await db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update preferences"
        ) from e


@router.get("/", response_model=Dict[str, SettingResponse])
async def get_settings(db_session: AsyncSession = Depends(get_db_session)) -> Dict[str, SettingResponse]:
    """
    Get all custom settings.

    Returns a dictionary where keys are setting names and values are setting objects.
    """
    try:
        query = select(Setting)
        result = await db_session.execute(query)
        settings = result.scalars().all()

        return {
            setting.key: SettingResponse(
                key=setting.key, value=setting.value, description=setting.description, setting_type=setting.setting_type
            )
            for setting in settings
        }

    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve settings"
        ) from e


@router.get("/{setting_key}", response_model=SettingResponse)
async def get_setting(setting_key: str, db_session: AsyncSession = Depends(get_db_session)) -> SettingResponse:
    """
    Get a specific setting by key.

    - **setting_key**: The key of the setting to retrieve
    """
    try:
        query = select(Setting).where(Setting.key == setting_key)
        result = await db_session.execute(query)
        setting = result.scalar_one_or_none()

        if not setting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Setting '{setting_key}' not found")

        return SettingResponse(
            key=setting.key, value=setting.value, description=setting.description, setting_type=setting.setting_type
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get setting '{setting_key}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve setting '{setting_key}'"
        ) from e


@router.put("/{setting_key}", response_model=SettingResponse)
async def update_setting(
    setting_key: str, update_request: SettingUpdateRequest, db_session: AsyncSession = Depends(get_db_session)
) -> SettingResponse:
    """
    Update or create a setting.

    - **setting_key**: The key of the setting to update or create
    - **value**: The new value for the setting
    - **description**: Optional description of the setting
    """
    try:
        # Check if setting exists
        query = select(Setting).where(Setting.key == setting_key)
        result = await db_session.execute(query)
        setting = result.scalar_one_or_none()

        if setting:
            # Update existing setting
            if update_request.value is not None:
                setting.value = update_request.value
            if update_request.description is not None:
                setting.description = update_request.description
        else:
            # Create new setting
            setting = Setting(key=setting_key, value=update_request.value, description=update_request.description)
            db_session.add(setting)

        await db_session.commit()
        await db_session.refresh(setting)

        logger.info(f"Updated setting '{setting_key}' = '{setting.value}'")

        return SettingResponse(
            key=setting.key, value=setting.value, description=setting.description, setting_type=setting.setting_type
        )

    except Exception as e:
        logger.error(f"Failed to update setting '{setting_key}': {e}")
        await db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update setting '{setting_key}'"
        ) from e


@router.delete("/{setting_key}")
async def delete_setting(setting_key: str, db_session: AsyncSession = Depends(get_db_session)) -> Dict[str, str]:
    """
    Delete a setting.

    - **setting_key**: The key of the setting to delete
    """
    try:
        query = select(Setting).where(Setting.key == setting_key)
        result = await db_session.execute(query)
        setting = result.scalar_one_or_none()

        if not setting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Setting '{setting_key}' not found")

        await db_session.delete(setting)
        await db_session.commit()

        logger.info(f"Deleted setting '{setting_key}'")

        return {"message": f"Setting '{setting_key}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete setting '{setting_key}': {e}")
        await db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete setting '{setting_key}'"
        ) from e


@router.get("/failed-logs/count")
async def get_failed_logs_count(db_session: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Get count of failed or stuck log entries.

    Returns counts for logs in FAILED, TRANSCRIBING, VECTORIZING, or SUMMARIZING status.
    """
    try:
        from app.models.log_entry import LogEntry, ProcessingStatus
        from sqlalchemy import func, or_

        # Query for failed/stuck logs
        query = select(func.count(LogEntry.id)).where(
            or_(
                LogEntry.processing_status == ProcessingStatus.FAILED,
                LogEntry.processing_status == ProcessingStatus.TRANSCRIBING,
                LogEntry.processing_status == ProcessingStatus.VECTORIZING,
                LogEntry.processing_status == ProcessingStatus.SUMMARIZING,
            )
        )

        result = await db_session.execute(query)
        total_count = result.scalar()

        # Get counts by status
        status_counts = {}
        for status in [
            ProcessingStatus.FAILED,
            ProcessingStatus.TRANSCRIBING,
            ProcessingStatus.VECTORIZING,
            ProcessingStatus.SUMMARIZING,
        ]:
            status_query = select(func.count(LogEntry.id)).where(LogEntry.processing_status == status)
            status_result = await db_session.execute(status_query)
            count = status_result.scalar()
            if count > 0:
                status_counts[status.value] = count

        return {"total": total_count, "by_status": status_counts}

    except Exception as e:
        logger.error(f"Failed to get failed logs count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve failed logs count"
        ) from e


@router.get("/initialization-status")
async def get_initialization_status(
    db_session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get initialization status for the application.

    Checks if all required settings are configured:
    - OpenAI API key (from environment)
    - AWS credentials (from environment or database)
    - S3 bucket name (from environment or database)

    Returns:
        - is_complete: bool indicating if initialization is complete
        - missing_settings: list of missing required settings
        - details: dict with details about each required setting
    """
    try:
        from app.services.settings_service import SettingsService
        from app.config import settings as env_settings

        settings_service = SettingsService(env_settings, db_session)

        status = await settings_service.get_initialization_status()

        return status

    except Exception as e:
        logger.error(f"Failed to get initialization status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve initialization status"
        ) from e
