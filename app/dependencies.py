"""FastAPI dependency providers."""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.log_entry import Base
from app.services.s3 import S3Service
from app.services.openai_client import OpenAIService


# Global variables for dependency injection
_settings: Settings = None
_async_session_maker = None
_db_engine = None


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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        ) from e


def get_s3_service(settings: Settings = Depends(get_settings)) -> S3Service:
    """Get S3 service instance."""
    return S3Service(settings)


def get_openai_service(settings: Settings = Depends(get_settings)) -> OpenAIService:
    """Get OpenAI service instance.""" 
    return OpenAIService(settings)


# Cleanup function for graceful shutdown
async def close_db_connection():
    """Close database connections on shutdown."""
    global _db_engine
    if _db_engine:
        await _db_engine.dispose()
        _db_engine = None