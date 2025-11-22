import enum
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Enum, Integer, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from .log_entry import Base


class MediaStorageMode(enum.Enum):
    """Media storage configuration modes."""

    S3_ONLY = "s3_only"
    LOCAL_WITH_S3 = "local_with_s3"


class Setting(Base):
    """Database model for application settings."""

    __tablename__ = "settings"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Settings key-value store
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    setting_type = Column(String(50), nullable=False, default="string")  # string, integer, boolean, json

    def __repr__(self):
        return f"<Setting(key={self.key}, value={self.value})>"


class UserPreferences(Base):
    """Database model for user-configurable preferences."""

    __tablename__ = "user_preferences"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Application preferences
    app_name = Column(String(255), nullable=False, default="Captain's Log")
    vessel_name = Column(String(255), nullable=False, default="SV DEFIANT")
    vessel_designation = Column(String(255), nullable=False, default="NCC-75633")

    # OpenAI model preferences
    openai_model_whisper = Column(String(100), nullable=False, default="whisper-1")
    openai_model_embedding = Column(String(100), nullable=False, default="text-embedding-3-small")
    openai_model_chat = Column(String(100), nullable=False, default="gpt-4o-mini")

    # Media storage preferences
    media_storage_mode = Column(Enum(MediaStorageMode), nullable=False, default=MediaStorageMode.S3_ONLY)
    local_media_path = Column(String(500), nullable=True, default="./media")

    # File size limits (in bytes)
    max_audio_file_size = Column(Integer, nullable=False, default=100 * 1024 * 1024)  # 100MB
    max_video_file_size = Column(Integer, nullable=False, default=1024 * 1024 * 1024)  # 1GB

    # Allowed file formats (JSON arrays)
    allowed_audio_formats = Column(JSON, nullable=False, default=["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"])
    allowed_video_formats = Column(JSON, nullable=False, default=["mp4", "webm", "mov", "avi"])

    # Pagination settings
    default_page_size = Column(Integer, nullable=False, default=20)
    max_page_size = Column(Integer, nullable=False, default=100)

    # Network resilience settings
    enable_resilient_processing = Column(Boolean, nullable=False, default=True)
    max_network_retries = Column(Integer, nullable=False, default=10)
    network_retry_base_delay = Column(Integer, nullable=False, default=30)
    network_retry_max_delay = Column(Integer, nullable=False, default=3600)

    # AWS/S3 settings that can be user-configurable
    aws_access_key_id = Column(String(255), nullable=True)
    aws_secret_access_key = Column(String(255), nullable=True)
    aws_region = Column(String(50), nullable=True, default="us-east-2")
    s3_bucket_name = Column(String(255), nullable=True)
    s3_audio_prefix = Column(String(100), nullable=False, default="audio/")
    s3_video_prefix = Column(String(100), nullable=False, default="video/")
    s3_presigned_url_expiry = Column(Integer, nullable=False, default=3600)

    # Authentication settings
    allow_new_user_registration = Column(Boolean, nullable=False, default=True)
    secret_key = Column(String(255), nullable=True)
    session_cookie_name = Column(String(100), nullable=False, default="captains_log_session")
    session_max_age = Column(Integer, nullable=False, default=2592000)

    # OAuth settings (optional, can be set via environment or UI)
    google_oauth_client_id = Column(String(255), nullable=True)
    google_oauth_client_secret = Column(String(255), nullable=True)
    facebook_oauth_client_id = Column(String(255), nullable=True)
    facebook_oauth_client_secret = Column(String(255), nullable=True)
    github_oauth_client_id = Column(String(255), nullable=True)
    github_oauth_client_secret = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<UserPreferences(id={self.id}, app_name={self.app_name})>"
