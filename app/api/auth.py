"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    auth_backend,
    fastapi_users,
    get_google_oauth_client,
    get_github_oauth_client,
    get_facebook_oauth_client,
    get_user_manager,
    get_user_db,
)
from app.config import settings
from app.dependencies import get_db_session
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter()


# Custom login endpoint with better error handling
@router.post("/auth/jwt/login")
async def login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Custom login endpoint with user-friendly error messages.

    Supports login with either username or email.
    Returns proper error messages for authentication failures instead of generic HTTP exceptions.
    """
    try:
        # Get user database and manager
        user_db = await anext(get_user_db(db_session))
        user_manager = await anext(get_user_manager(user_db))

        # Try to find user by username first, then by email
        user = await db_session.execute(
            select(User).where(User.username == credentials.username)
        )
        user = user.scalar_one_or_none()

        # If not found by username, try email
        if user is None:
            user = await db_session.execute(
                select(User).where(User.email == credentials.username)
            )
            user = user.scalar_one_or_none()

        # Verify user exists, is active, and password is correct
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid username and/or password"
            )

        # Verify password using the user manager's password helper
        valid, updated_password_hash = user_manager.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )

        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid username and/or password"
            )

        # Update password hash if it was rehashed with updated algorithm
        if updated_password_hash is not None:
            user.hashed_password = updated_password_hash
            db_session.add(user)
            await db_session.commit()

        # Generate authentication response
        strategy = auth_backend.get_strategy()
        login_response = await auth_backend.login(strategy, user)

        return login_response

    except HTTPException:
        # Re-raise our custom HTTP exceptions
        raise
    except Exception as e:
        # Catch any other errors and return user-friendly message
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username and/or password"
        )


# Register logout route from fastapi_users
@router.post("/auth/jwt/logout")
async def logout(
    user: User = Depends(fastapi_users.current_user(active=True)),
):
    """Logout endpoint."""
    # Return response that clears the authentication cookie
    from app.auth import cookie_transport
    return await cookie_transport.get_logout_response()


# Custom registration endpoint with toggle check
@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Register a new user.

    Checks if registration is allowed:
    - Always allows first user (when count = 0)
    - Requires allow_new_user_registration = True for subsequent users
    """
    # Count existing users
    result = await db_session.execute(select(func.count(User.id)))
    user_count = result.scalar()

    # Check if registration is allowed
    if user_count > 0 and not settings.allow_new_user_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="New user registration is currently disabled")

    # Use fastapi_users registration endpoint
    from app.auth import get_user_manager, get_user_db

    user_db = await anext(get_user_db(db_session))
    user_manager = await anext(get_user_manager(user_db))

    try:
        user = await user_manager.create(user_create)
        return UserRead.model_validate(user)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# User management routes
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# Verification routes (optional, can be disabled)
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)

# Password reset routes (optional)
router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

def register_oauth_routes():
    """
    Register OAuth routes for configured providers.

    This function should be called after loading OAuth credentials from the database
    to ensure all configured providers are properly registered.
    """
    # OAuth routes - only add if credentials are configured
    google_oauth_client = get_google_oauth_client()
    if google_oauth_client:
        router.include_router(
            fastapi_users.get_oauth_router(
                google_oauth_client,
                auth_backend,
                settings.secret_key,
            ),
            prefix="/auth/google",
            tags=["auth", "oauth"],
        )

    github_oauth_client = get_github_oauth_client()
    if github_oauth_client:
        router.include_router(
            fastapi_users.get_oauth_router(
                github_oauth_client,
                auth_backend,
                settings.secret_key,
            ),
            prefix="/auth/github",
            tags=["auth", "oauth"],
        )

    facebook_oauth_client = get_facebook_oauth_client()
    if facebook_oauth_client:
        router.include_router(
            fastapi_users.get_oauth_router(
                facebook_oauth_client,
                auth_backend,
                settings.secret_key,
            ),
            prefix="/auth/facebook",
            tags=["auth", "oauth"],
        )


# Call this immediately to register any OAuth routes configured via environment variables
register_oauth_routes()
