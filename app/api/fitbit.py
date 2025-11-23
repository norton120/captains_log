"""Fitbit API endpoints."""
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.dependencies import get_db_session
from app.models.user import User
from app.models.fitbit import UserFitbitSettings, FitbitData
from app.models.log_entry import LogEntry
from app.services.fitbit_service import FitbitService, FitbitAPIError
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fitbit", tags=["fitbit"])


class SelectDeviceRequest(BaseModel):
    """Request model for selecting a Fitbit device."""
    device_id: str


class FitbitStatusResponse(BaseModel):
    """Response model for Fitbit connection status."""
    is_authorized: bool
    fitbit_user_id: Optional[str] = None
    device_id: Optional[str] = None


@router.get("/authorize")
async def authorize_fitbit(
    request: Request,
    user: User = Depends(current_active_user),
):
    """
    Redirect to Fitbit OAuth authorization page.
    """
    fitbit_settings = settings

    if not settings.fitbit_oauth_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fitbit OAuth is not configured",
        )

    fitbit_service = FitbitService(settings)

    # Generate redirect URI
    redirect_uri = str(request.url_for("fitbit_callback"))

    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    request.session["fitbit_oauth_state"] = state

    # Get authorization URL
    auth_url = fitbit_service.get_authorization_url(redirect_uri, state)

    return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback")
async def fitbit_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Handle Fitbit OAuth callback.
    """
    fitbit_settings = settings

    # Check for error from Fitbit
    if error:
        logger.error(f"Fitbit OAuth error: {error} - {error_description}")
        request.session["fitbit_error"] = error_description or "Authorization failed"
        return RedirectResponse(url="/settings", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Verify we have a code
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )

    # Verify state (CSRF protection)
    session_state = request.session.get("fitbit_oauth_state")
    if state != session_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    # Exchange code for tokens
    fitbit_service = FitbitService(settings)
    redirect_uri = str(request.url_for("fitbit_callback"))

    try:
        await fitbit_service.exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            user_id=user.id,
            db=db,
        )

        request.session["fitbit_success"] = "Fitbit connected successfully!"

    except FitbitAPIError as e:
        logger.error(f"Failed to exchange code: {e}")
        request.session["fitbit_error"] = "Failed to connect Fitbit"

    return RedirectResponse(url="/settings", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/devices")
async def get_fitbit_devices(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get list of user's Fitbit devices.
    """
    fitbit_settings = settings
    fitbit_service = FitbitService(settings)

    # Get user settings
    result = await db.execute(
        select(UserFitbitSettings).where(UserFitbitSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fitbit not authorized. Please connect your Fitbit first.",
        )

    try:
        devices = await fitbit_service.get_user_devices_with_refresh(user.id, db)
        return devices
    except FitbitAPIError as e:
        logger.error(f"Failed to get devices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Fitbit devices",
        )


@router.post("/device/select")
async def select_fitbit_device(
    request: SelectDeviceRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Select a Fitbit device for the user.
    """
    result = await db.execute(
        select(UserFitbitSettings).where(UserFitbitSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fitbit not authorized",
        )

    user_settings.fitbit_device_id = request.device_id
    await db.commit()

    return {"device_id": request.device_id, "message": "Device selected successfully"}


@router.post("/disconnect")
async def disconnect_fitbit(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Disconnect Fitbit integration for the user.
    """
    result = await db.execute(
        select(UserFitbitSettings).where(UserFitbitSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if user_settings:
        user_settings.clear_tokens()
        await db.commit()

    return {"message": "Fitbit disconnected successfully"}


@router.get("/status", response_model=FitbitStatusResponse)
async def get_fitbit_status(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get Fitbit connection status for the user.
    """
    result = await db.execute(
        select(UserFitbitSettings).where(UserFitbitSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.is_authorized:
        return FitbitStatusResponse(is_authorized=False)

    return FitbitStatusResponse(
        is_authorized=True,
        fitbit_user_id=user_settings.fitbit_user_id,
        device_id=user_settings.fitbit_device_id,
    )


@router.post("/capture-historical/{log_id}")
async def capture_historical_fitbit_data(
    log_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Capture Fitbit data for an existing log entry (historical capture).
    """
    fitbit_settings = settings

    # Check if user has Fitbit authorized
    result = await db.execute(
        select(UserFitbitSettings).where(UserFitbitSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fitbit not authorized",
        )

    # Get the log entry
    log_result = await db.execute(
        select(LogEntry).where(LogEntry.id == log_id, LogEntry.user_id == user.id)
    )
    log = log_result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log entry not found",
        )

    # Check if Fitbit data already exists
    fitbit_result = await db.execute(
        select(FitbitData).where(FitbitData.log_entry_id == log_id)
    )
    existing_fitbit_data = fitbit_result.scalar_one_or_none()

    if existing_fitbit_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This log already has Fitbit data",
        )

    # Capture Fitbit data
    fitbit_service = FitbitService(settings)

    try:
        # Refresh token if needed
        if user_settings.is_token_expired():
            await fitbit_service.refresh_access_token(user.id, db)
            await db.refresh(user_settings)

        # Get health snapshot
        health_data = await fitbit_service.get_comprehensive_health_snapshot(
            user_settings.access_token
        )

        # Create FitbitData record
        from datetime import datetime, UTC

        fitbit_data = FitbitData(
            id=uuid.uuid4(),
            log_entry_id=log_id,
            user_id=user.id,
            captured_at=datetime.now(UTC),
            **health_data,
        )

        db.add(fitbit_data)
        await db.commit()

        return {"fitbit_data_id": str(fitbit_data.id), "message": "Fitbit data captured successfully"}

    except FitbitAPIError as e:
        logger.error(f"Failed to capture historical Fitbit data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to capture Fitbit data",
        )
