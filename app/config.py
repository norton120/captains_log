from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Application settings
    app_name: str = Field(default="Captain's Log", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Database settings
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/captains_log",
        description="PostgreSQL database URL with pgvector support"
    )
    
    # OpenAI settings
    openai_api_key: str = Field(..., description="OpenAI API key for Whisper and embeddings")
    openai_model_whisper: str = Field(default="whisper-1", description="OpenAI Whisper model")
    openai_model_embedding: str = Field(default="text-embedding-3-small", description="OpenAI embedding model")
    openai_model_chat: str = Field(default="gpt-4o-mini", description="OpenAI chat model for summaries")
    
    # AWS S3 settings (using session/IAM role authentication)
    aws_region: str = Field(default="us-east-2", description="AWS Region")
    s3_bucket_name: str = Field(..., description="S3 bucket name for audio storage")
    s3_audio_prefix: str = Field(default="audio/", description="S3 prefix for audio files")
    s3_presigned_url_expiry: int = Field(default=3600, description="Presigned URL expiry in seconds")
    
    # DBOS settings
    dbos_app_name: str = Field(default="captains-log", description="DBOS application name")
    dbos_database_url: Optional[str] = Field(default=None, description="DBOS database URL (defaults to main database)")
    
    # Audio processing settings
    max_audio_file_size: int = Field(default=100 * 1024 * 1024, description="Max audio file size in bytes (100MB)")
    allowed_audio_formats: list[str] = Field(
        default=["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"],
        description="Allowed audio file formats"
    )
    
    # Pagination settings
    default_page_size: int = Field(default=20, description="Default page size for pagination")
    max_page_size: int = Field(default=100, description="Maximum page size for pagination")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()