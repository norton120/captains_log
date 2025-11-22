"""Middleware for application initialization and security."""
import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import SettingsService
from app.config import settings as env_settings
from app.dependencies import get_db_session

logger = logging.getLogger(__name__)


class InitializationCheckMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check if application initialization is complete.

    If required settings are missing, redirects all non-whitelisted routes
    to the settings page with an initialization flag.

    Whitelisted routes that don't require initialization:
    - /auth/* (authentication routes)
    - /settings (settings page)
    - /api/settings/* (settings API)
    - /health (health check)
    - /static/* (static assets)
    """

    WHITELISTED_PATHS = [
        "/auth/",
        "/settings",
        "/api/settings/",
        "/health",
        "/static/",
        "/docs",  # FastAPI docs
        "/openapi.json",  # FastAPI OpenAPI spec
        "/redoc",  # FastAPI redoc
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check initialization status and redirect if needed."""
        path = request.url.path

        # Skip check for whitelisted paths
        if any(path.startswith(wp) for wp in self.WHITELISTED_PATHS):
            return await call_next(request)

        # Get database session
        try:
            # Create a new database session for this request
            from app.database import async_session_maker
            async with async_session_maker() as db_session:
                settings_service = SettingsService(env_settings, db_session)

                # Check if initialization is complete
                is_complete = await settings_service.is_initialization_complete()

                if not is_complete:
                    # Redirect to settings with init flag
                    logger.info(f"Initialization incomplete, redirecting {path} to /settings?init=true")
                    return RedirectResponse(url="/settings?init=true", status_code=302)

        except Exception as e:
            # Log error but don't block the request
            logger.error(f"Error checking initialization status: {e}")
            # Continue with the request if we can't check status
            pass

        # Proceed with the request
        return await call_next(request)
