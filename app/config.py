import enum
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from pathlib import Path


class MediaStorageMode(enum.Enum):
    """Media storage configuration modes."""
    S3_ONLY = "s3_only"
    LOCAL_WITH_S3 = "local_with_s3"


class Settings(BaseSettings):
    # Application settings
    app_name: str = Field(default="Captain's Log", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Database settings
    database_url: str = Field(
        default="postgresql+asyncpg://captain:defiant@db:5432/captains_log",
        description="PostgreSQL database URL with pgvector support"
    )
    
    # OpenAI settings
    openai_api_key: str = Field(..., description="OpenAI API key for Whisper and embeddings")
    openai_model_whisper: str = Field(default="whisper-1", description="OpenAI Whisper model")
    openai_model_embedding: str = Field(default="text-embedding-3-small", description="OpenAI embedding model")
    openai_model_chat: str = Field(default="gpt-4o-mini", description="OpenAI chat model for summaries")
    
    # AWS S3 settings
    aws_region: str = Field(default="us-east-2", description="AWS Region")
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS Access Key ID (optional if using IAM roles)")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS Secret Access Key (optional if using IAM roles)")
    s3_bucket_name: str = Field(default="captains-log-audio", description="S3 bucket name for audio storage")
    s3_audio_prefix: str = Field(default="audio/", description="S3 prefix for audio files")
    s3_video_prefix: str = Field(default="video/", description="S3 prefix for video files")
    s3_presigned_url_expiry: int = Field(default=3600, description="Presigned URL expiry in seconds")
    
    # DBOS settings
    dbos_app_name: str = Field(default="captains-log", description="DBOS application name")
    dbos_database_url: Optional[str] = Field(default=None, description="DBOS database URL (defaults to main database)")
    
    # Network resilience settings
    enable_resilient_processing: bool = Field(default=True, description="Enable network-resilient processing")
    max_network_retries: int = Field(default=10, description="Maximum retry attempts for network operations")
    network_retry_base_delay: int = Field(default=30, description="Base delay for network retries in seconds")
    network_retry_max_delay: int = Field(default=3600, description="Maximum delay for network retries in seconds")
    
    # Media storage settings
    media_storage_mode: MediaStorageMode = Field(
        default=MediaStorageMode.S3_ONLY,
        description="Media storage mode: s3_only or local_with_s3"
    )
    local_media_path: Optional[str] = Field(
        default="./media",
        description="Local path for media storage when using local_with_s3 mode"
    )
    
    # Audio processing settings
    max_audio_file_size: int = Field(default=100 * 1024 * 1024, description="Max audio file size in bytes (100MB)")
    allowed_audio_formats: list[str] = Field(
        default=["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"],
        description="Allowed audio file formats"
    )
    
    # Video processing settings
    max_video_file_size: int = Field(default=1024 * 1024 * 1024, description="Max video file size in bytes (1GB)")
    allowed_video_formats: list[str] = Field(
        default=["mp4", "webm", "mov", "avi"],
        description="Allowed video file formats"
    )
    
    # Pagination settings
    default_page_size: int = Field(default=20, description="Default page size for pagination")
    max_page_size: int = Field(default=100, description="Maximum page size for pagination")
    
    @validator("local_media_path")
    def validate_local_media_path(cls, v, values):
        """Validate local media path when using local_with_s3 mode."""
        mode = values.get("media_storage_mode")
        if mode == MediaStorageMode.LOCAL_WITH_S3:
            if not v:
                raise ValueError("local_media_path is required when using local_with_s3 mode")
            
            # Convert to Path and validate it can be created
            path = Path(v).resolve()  # Convert to absolute path
            try:
                path.mkdir(parents=True, exist_ok=True)
                if not path.is_dir():
                    raise ValueError(f"local_media_path is not a directory: {path}")
            except Exception as e:
                raise ValueError(f"Cannot create local_media_path {path}: {e}")
        
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()