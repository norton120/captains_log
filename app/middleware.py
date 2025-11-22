"""Middleware for application initialization and security."""

import logging
from typing import Callable, Optional
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
    - /api/auth/* (authentication routes)
    - /login (login page)
    - /signup (signup page)
    - /settings (settings page)
    - /api/settings/* (settings API)
    - /health (health check)
    - /static/* (static assets)
    - /docs, /openapi.json, /redoc (API documentation)
    """

    WHITELISTED_PATHS = [
        "/api/auth/",  # Authentication routes (login, register, OAuth)
        "/login",  # Login page
        "/signup",  # Signup page
        "/settings",  # Settings page (accessible during initialization)
        "/api/settings/",  # Settings API (accessible during initialization)
        "/health",  # Health check
        "/static/",  # Static assets
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


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to require authentication for all routes except whitelisted ones.

    Redirects unauthenticated users to the login page.

    Whitelisted routes that don't require authentication:
    - /api/auth/* (authentication routes)
    - /login (login page)
    - /signup (signup page)
    - /health (health check)
    - /static/* (static assets)
    - /docs, /openapi.json, /redoc (API documentation)
    """

    WHITELISTED_PATHS = [
        "/api/auth/",  # Authentication routes (login, register, OAuth)
        "/login",  # Login page
        "/signup",  # Signup page
        "/health",  # Health check
        "/static/",  # Static assets
        "/docs",  # FastAPI docs
        "/openapi.json",  # FastAPI OpenAPI spec
        "/redoc",  # FastAPI redoc
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check if user is authenticated and redirect if needed."""
        path = request.url.path

        # Skip check for whitelisted paths
        if any(path.startswith(wp) for wp in self.WHITELISTED_PATHS):
            return await call_next(request)

        # Check if user is authenticated via request.state.user (set by UserContextMiddleware)
        user = getattr(request.state, "user", None)

        if not user:
            # User is not authenticated, redirect to login
            logger.info(f"Unauthenticated access to {path}, redirecting to /login")
            return RedirectResponse(url=f"/login?next={path}", status_code=302)

        # User is authenticated, proceed with the request
        return await call_next(request)


class UserContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject current user into request state for templates.

    This middleware attempts to extract the authenticated user from the
    request and makes it available in request.state.user for use in
    template contexts.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add current user to request state."""
        from app.models.user import User

        # Try to get the current user (if authenticated)
        user: Optional[User] = None

        try:
            # Import auth components
            from app.auth import auth_backend

            # Try to extract the token from the cookie
            token = await auth_backend.transport.get_login_response(request)

            if token:
                # Decode the token to get user_id
                from app.auth import get_jwt_strategy

                strategy = get_jwt_strategy()
                user_token_data = await strategy.read_token(token, user_manager=None)

                if user_token_data:
                    # Get user from database
                    from app.database import async_session_maker
                    from sqlalchemy import select

                    async with async_session_maker() as db_session:
                        result = await db_session.execute(select(User).where(User.id == user_token_data))
                        user = result.scalar_one_or_none()

        except Exception as e:
            # If there's any error getting the user, just set it to None
            logger.debug(f"Could not get user from request: {e}")
            user = None

        # Store user in request state
        request.state.user = user

        # Proceed with the request
        return await call_next(request)
