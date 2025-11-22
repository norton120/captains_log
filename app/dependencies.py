"""FastAPI dependency providers."""
from typing import AsyncGenerator, Generator
from fastapi import Depends, HTTPException, status
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.log_entry import Base
from app.models.user import User
from app.services.s3 import S3Service
from app.services.media_storage import MediaStorageService
from app.services.openai_client import OpenAIService
from app.services.settings_service import SettingsService, SettingsAdapter


# Global variables for dependency injection
_settings: Settings = None
_async_session_maker = None
_db_engine = None
_sync_db_engine = None
_sync_session_maker = None


def get_settings() -> Settings:
    """Get application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


async def get_db_engine():
    """Get database engine."""
    global _db_engine
    if _db_engine is None:
        settings = get_settings()
        _db_engine = create_async_engine(
            settings.database_url,
            poolclass=StaticPool if settings.database_url.startswith("sqlite") else None,
            connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
            echo=settings.debug,
        )
        
        # Create tables if they don't exist
        async with _db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    return _db_engine


async def get_async_session_maker():
    """Get async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = await get_db_engine()
        _async_session_maker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    try:
        session_maker = await get_async_session_maker()
        async with session_maker() as session:
            yield session
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Database session error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {type(e).__name__}"
        ) from e


def get_sync_db_engine():
    """Get synchronous database engine for template routes."""
    global _sync_db_engine
    if _sync_db_engine is None:
        settings = get_settings()
        # Convert async URL to sync URL
        sync_url = settings.database_url.replace('postgresql+asyncpg://', 'postgresql://')
        _sync_db_engine = create_engine(
            sync_url,
            poolclass=StaticPool if sync_url.startswith("sqlite") else None,
            connect_args={"check_same_thread": False} if sync_url.startswith("sqlite") else {},
            echo=settings.debug,
        )
    return _sync_db_engine


def get_sync_session_maker():
    """Get synchronous session maker."""
    global _sync_session_maker
    if _sync_session_maker is None:
        engine = get_sync_db_engine()
        _sync_session_maker = sessionmaker(bind=engine, expire_on_commit=False)
    return _sync_session_maker


def get_db() -> Generator[Session, None, None]:
    """Get synchronous database session for template routes."""
    session_maker = get_sync_session_maker()
    session = session_maker()
    try:
        yield session
    finally:
        session.close()


def get_s3_service(settings: Settings = Depends(get_settings)) -> S3Service:
    """Get S3 service instance."""
    return S3Service(settings)


def get_openai_service(settings: Settings = Depends(get_settings)) -> OpenAIService:
    """Get OpenAI service instance.""" 
    return OpenAIService(settings)


def get_media_storage_service(settings: Settings = Depends(get_settings)) -> MediaStorageService:
    """Get media storage service instance."""
    return MediaStorageService(settings)


async def get_enhanced_settings(
    env_settings: Settings = Depends(get_settings),
    db_session: AsyncSession = Depends(get_db_session)
) -> SettingsAdapter:
    """Get enhanced settings that combine environment and database settings."""
    settings_service = SettingsService(env_settings, db_session)
    
    # Load user preferences into cache
    await settings_service.get_user_preferences()
    
    return SettingsAdapter(settings_service)


async def get_current_user(
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Get the current logged-in user.

    For now, this returns the first user in the database (since all apps should
    have exactly 1 user). In the future, this will be replaced with actual
    authentication logic.
    """
    # Get the first user (there should be exactly one)
    result = await db_session.execute(select(User).limit(1))
    user = result.scalar_one_or_none()

    # If no user exists, create the generic user
    if user is None:
        user = User(
            username="generic_user",
            email="generic@captainslog.local"
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return user


def verify_log_ownership(log_entry, current_user: User) -> None:
    """
    Verify that the current user owns the log entry.

    Uses the OOP approach by checking if the log is in the user's authored_logs.

    Raises HTTPException with 403 status if the user doesn't own the log entry.
    """
    # Check if log is in user's authored logs by comparing user_id
    # This avoids loading the entire relationship
    if log_entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this log entry"
        )


# Cleanup function for graceful shutdown
async def close_db_connection():
    """Close database connections on shutdown."""
    global _db_engine, _sync_db_engine
    if _db_engine:
        await _db_engine.dispose()
        _db_engine = None
    if _sync_db_engine:
        _sync_db_engine.dispose()
        _sync_db_engine = None