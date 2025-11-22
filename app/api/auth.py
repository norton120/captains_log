"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    auth_backend,
    fastapi_users,
    get_google_oauth_client,
    get_github_oauth_client,
    get_facebook_oauth_client,
)
from app.config import settings
from app.dependencies import get_db_session
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter()

# Register the auth routes from fastapi_users
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)


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
