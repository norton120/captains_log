"""Authentication setup using FastAPI Users."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from httpx_oauth.clients.facebook import FacebookOAuth2
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db_session
from app.models.user import User
from app.schemas.user import UserCreate


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    """User manager for handling user operations."""

    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Called after a user has been registered."""
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Called after a user has requested a password reset."""
        print(f"User {user.id} has forgotten their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Called after a user has requested verification."""
        print(f"Verification requested for user {user.id}. Verification token: {token}")

    async def create(
        self,
        user_create: UserCreate,
        safe: bool = False,
        request: Optional[Request] = None,
    ) -> User:
        """
        Create a user with registration toggle enforcement.

        Always allows first user creation (when count = 0).
        Enforces allow_new_user_registration setting for subsequent users.
        """
        # Count existing users
        from sqlalchemy import select, func
        db_session = request.state.db_session if request else None

        if db_session:
            result = await db_session.execute(select(func.count(User.id)))
            user_count = result.scalar()

            # If users exist and registration is disabled, raise error
            if user_count > 0 and not settings.allow_new_user_registration:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="New user registration is currently disabled"
                )

        # Proceed with user creation
        return await super().create(user_create, safe=safe, request=request)


async def get_user_db(session: AsyncSession = Depends(get_db_session)):
    """Get the user database adapter."""
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Get the user manager."""
    yield UserManager(user_db)


# Cookie transport for session-based authentication
cookie_transport = CookieTransport(
    cookie_name=settings.session_cookie_name,
    cookie_max_age=settings.session_max_age,
    cookie_httponly=True,
    cookie_secure=False,  # Set to True in production with HTTPS
    cookie_samesite="lax",
)


def get_jwt_strategy() -> JWTStrategy:
    """Get JWT strategy for authentication."""
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.session_max_age,
    )


# Authentication backend
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPI Users instance
fastapi_users = FastAPIUsers[User, UUID](
    get_user_manager,
    [auth_backend],
)

# Current user dependencies
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)

# Optional current user (for pages that work with or without login)
optional_current_user = fastapi_users.current_user(optional=True)


def get_google_oauth_client() -> Optional[GoogleOAuth2]:
    """
    Get Google OAuth client if configured.

    Checks environment variables (via settings) first.
    DB-stored OAuth credentials in UserPreferences can also be used
    but require application restart to take effect.
    """
    if settings.google_oauth_client_id and settings.google_oauth_client_secret:
        return GoogleOAuth2(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
        )
    return None


def get_github_oauth_client() -> Optional[GitHubOAuth2]:
    """
    Get GitHub OAuth client if configured.

    Checks environment variables (via settings) first.
    DB-stored OAuth credentials in UserPreferences can also be used
    but require application restart to take effect.
    """
    if settings.github_oauth_client_id and settings.github_oauth_client_secret:
        return GitHubOAuth2(
            settings.github_oauth_client_id,
            settings.github_oauth_client_secret,
        )
    return None


def get_facebook_oauth_client() -> Optional[FacebookOAuth2]:
    """
    Get Facebook OAuth client if configured.

    Checks environment variables (via settings) first.
    DB-stored OAuth credentials in UserPreferences can also be used
    but require application restart to take effect.
    """
    if settings.facebook_oauth_client_id and settings.facebook_oauth_client_secret:
        return FacebookOAuth2(
            settings.facebook_oauth_client_id,
            settings.facebook_oauth_client_secret,
        )
    return None
