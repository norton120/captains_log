"""Settings service for combining environment and database settings."""

import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import UserPreferences, Setting
from app.config import Settings as EnvSettings, MediaStorageMode

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings from both environment and database."""

    def __init__(self, env_settings: EnvSettings, db_session: AsyncSession):
        self.env_settings = env_settings
        self.db_session = db_session
        self._cached_preferences: Optional[UserPreferences] = None
        self._cached_settings: Dict[str, Setting] = {}

    async def get_user_preferences(self) -> UserPreferences:
        """Get user preferences from database, creating defaults if needed."""
        if self._cached_preferences is None:
            query = select(UserPreferences).limit(1)
            result = await self.db_session.execute(query)
            preferences = result.scalar_one_or_none()

            if not preferences:
                # Create default preferences
                preferences = UserPreferences()
                self.db_session.add(preferences)
                await self.db_session.commit()
                await self.db_session.refresh(preferences)
                logger.info("Created default user preferences")

            self._cached_preferences = preferences

        return self._cached_preferences

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a custom setting by key."""
        if key not in self._cached_settings:
            query = select(Setting).where(Setting.key == key)
            result = await self.db_session.execute(query)
            setting = result.scalar_one_or_none()

            if setting:
                self._cached_settings[key] = setting
            else:
                return default

        return self._cached_settings[key].value if self._cached_settings[key] else default

    def clear_cache(self):
        """Clear the cache to force reload from database."""
        self._cached_preferences = None
        self._cached_settings.clear()

    # Properties that combine environment and database settings

    @property
    def app_name(self) -> str:
        """Get application name from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.app_name
        return self.env_settings.app_name

    @property
    def vessel_name(self) -> str:
        """Get vessel name from preferences or default."""
        if self._cached_preferences:
            return self._cached_preferences.vessel_name
        return "SV DEFIANT"

    @property
    def vessel_designation(self) -> str:
        """Get vessel designation from preferences or default."""
        if self._cached_preferences:
            return self._cached_preferences.vessel_designation
        return "NCC-75633"

    @property
    def database_url(self) -> str:
        """Database URL always comes from environment for security."""
        return self.env_settings.database_url

    @property
    def openai_api_key(self) -> str:
        """OpenAI API key always comes from environment for security."""
        return self.env_settings.openai_api_key

    @property
    def openai_model_whisper(self) -> str:
        """Get Whisper model from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.openai_model_whisper
        return self.env_settings.openai_model_whisper

    @property
    def openai_model_embedding(self) -> str:
        """Get embedding model from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.openai_model_embedding
        return self.env_settings.openai_model_embedding

    @property
    def openai_model_chat(self) -> str:
        """Get chat model from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.openai_model_chat
        return self.env_settings.openai_model_chat

    @property
    def aws_region(self) -> str:
        """AWS region from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.aws_region:
            return self._cached_preferences.aws_region
        return self.env_settings.aws_region

    @property
    def aws_access_key_id(self) -> Optional[str]:
        """AWS access key from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.aws_access_key_id:
            return self._cached_preferences.aws_access_key_id
        return self.env_settings.aws_access_key_id

    @property
    def aws_secret_access_key(self) -> Optional[str]:
        """AWS secret key from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.aws_secret_access_key:
            return self._cached_preferences.aws_secret_access_key
        return self.env_settings.aws_secret_access_key

    @property
    def s3_bucket_name(self) -> str:
        """S3 bucket name from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.s3_bucket_name:
            return self._cached_preferences.s3_bucket_name
        return self.env_settings.s3_bucket_name

    @property
    def s3_audio_prefix(self) -> str:
        """Get S3 audio prefix from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.s3_audio_prefix
        return self.env_settings.s3_audio_prefix

    @property
    def s3_video_prefix(self) -> str:
        """Get S3 video prefix from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.s3_video_prefix
        return self.env_settings.s3_video_prefix

    @property
    def s3_presigned_url_expiry(self) -> int:
        """Get S3 presigned URL expiry from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.s3_presigned_url_expiry
        return self.env_settings.s3_presigned_url_expiry

    @property
    def media_storage_mode(self) -> MediaStorageMode:
        """Get media storage mode from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.media_storage_mode
        return self.env_settings.media_storage_mode

    @property
    def local_media_path(self) -> Optional[str]:
        """Get local media path from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.local_media_path
        return self.env_settings.local_media_path

    @property
    def max_audio_file_size(self) -> int:
        """Get max audio file size from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.max_audio_file_size
        return self.env_settings.max_audio_file_size

    @property
    def max_video_file_size(self) -> int:
        """Get max video file size from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.max_video_file_size
        return self.env_settings.max_video_file_size

    @property
    def allowed_audio_formats(self) -> List[str]:
        """Get allowed audio formats from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.allowed_audio_formats
        return self.env_settings.allowed_audio_formats

    @property
    def allowed_video_formats(self) -> List[str]:
        """Get allowed video formats from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.allowed_video_formats
        return self.env_settings.allowed_video_formats

    @property
    def default_page_size(self) -> int:
        """Get default page size from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.default_page_size
        return self.env_settings.default_page_size

    @property
    def max_page_size(self) -> int:
        """Get max page size from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.max_page_size
        return self.env_settings.max_page_size

    @property
    def enable_resilient_processing(self) -> bool:
        """Get resilient processing setting from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.enable_resilient_processing
        return self.env_settings.enable_resilient_processing

    @property
    def max_network_retries(self) -> int:
        """Get max network retries from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.max_network_retries
        return self.env_settings.max_network_retries

    @property
    def network_retry_base_delay(self) -> int:
        """Get network retry base delay from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.network_retry_base_delay
        return self.env_settings.network_retry_base_delay

    @property
    def network_retry_max_delay(self) -> int:
        """Get network retry max delay from preferences or environment."""
        if self._cached_preferences:
            return self._cached_preferences.network_retry_max_delay
        return self.env_settings.network_retry_max_delay

    # DBOS settings always come from environment for infrastructure

    @property
    def dbos_app_name(self) -> str:
        """DBOS app name always comes from environment."""
        return self.env_settings.dbos_app_name

    @property
    def dbos_database_url(self) -> Optional[str]:
        """DBOS database URL always comes from environment."""
        return self.env_settings.dbos_database_url

    @property
    def s3_base_url(self) -> Optional[str]:
        """S3 base URL from preferences for custom endpoints (e.g., MinIO)."""
        if self._cached_preferences and self._cached_preferences.s3_base_url:
            return self._cached_preferences.s3_base_url
        return None

    # OAuth/SSO settings (database first, then environment)

    @property
    def google_oauth_client_id(self) -> Optional[str]:
        """Google OAuth Client ID from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.google_oauth_client_id:
            return self._cached_preferences.google_oauth_client_id
        return self.env_settings.google_oauth_client_id

    @property
    def google_oauth_client_secret(self) -> Optional[str]:
        """Google OAuth Client Secret from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.google_oauth_client_secret:
            return self._cached_preferences.google_oauth_client_secret
        return self.env_settings.google_oauth_client_secret

    @property
    def github_oauth_client_id(self) -> Optional[str]:
        """GitHub OAuth Client ID from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.github_oauth_client_id:
            return self._cached_preferences.github_oauth_client_id
        return self.env_settings.github_oauth_client_id

    @property
    def github_oauth_client_secret(self) -> Optional[str]:
        """GitHub OAuth Client Secret from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.github_oauth_client_secret:
            return self._cached_preferences.github_oauth_client_secret
        return self.env_settings.github_oauth_client_secret

    @property
    def facebook_oauth_client_id(self) -> Optional[str]:
        """Facebook OAuth Client ID from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.facebook_oauth_client_id:
            return self._cached_preferences.facebook_oauth_client_id
        return self.env_settings.facebook_oauth_client_id

    @property
    def facebook_oauth_client_secret(self) -> Optional[str]:
        """Facebook OAuth Client Secret from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.facebook_oauth_client_secret:
            return self._cached_preferences.facebook_oauth_client_secret
        return self.env_settings.facebook_oauth_client_secret

    @property
    def fitbit_oauth_client_id(self) -> Optional[str]:
        """Fitbit OAuth Client ID from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.fitbit_oauth_client_id:
            return self._cached_preferences.fitbit_oauth_client_id
        return self.env_settings.fitbit_oauth_client_id

    @property
    def fitbit_oauth_client_secret(self) -> Optional[str]:
        """Fitbit OAuth Client Secret from preferences or environment."""
        if self._cached_preferences and self._cached_preferences.fitbit_oauth_client_secret:
            return self._cached_preferences.fitbit_oauth_client_secret
        return self.env_settings.fitbit_oauth_client_secret

    async def get_initialization_status(self) -> Dict[str, Any]:
        """
        Check if all required settings are configured for app initialization.

        Returns:
            dict with:
                - is_complete: bool indicating if initialization is complete
                - missing_settings: list of missing required settings
                - details: dict with details about each required setting
        """
        await self.get_user_preferences()  # Ensure preferences are loaded

        missing_settings = []
        details = {}

        # Check OpenAI API key (required, environment only)
        if not self.openai_api_key:
            missing_settings.append("openai_api_key")
            details["openai_api_key"] = {
                "name": "OpenAI API Key",
                "source": "environment",
                "required": True,
                "present": False,
            }
        else:
            details["openai_api_key"] = {
                "name": "OpenAI API Key",
                "source": "environment",
                "required": True,
                "present": True,
            }

        # Check AWS credentials (either env OR db, at least one method required)
        aws_creds_present = bool(
            (self.aws_access_key_id and self.aws_secret_access_key)
            or
            # Check if running in AWS with IAM role (env vars from boto would be set)
            self.env_settings.aws_access_key_id
        )

        if not aws_creds_present:
            missing_settings.append("aws_credentials")
            details["aws_credentials"] = {
                "name": "AWS Credentials",
                "source": "environment or database",
                "required": True,
                "present": False,
                "message": "Either set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in environment, or configure them in database settings",
            }
        else:
            source = "environment" if self.env_settings.aws_access_key_id else "database"
            details["aws_credentials"] = {
                "name": "AWS Credentials",
                "source": source,
                "required": True,
                "present": True,
            }

        # Check S3 bucket name
        if not self.s3_bucket_name:
            missing_settings.append("s3_bucket_name")
            details["s3_bucket_name"] = {
                "name": "S3 Bucket Name",
                "source": "environment or database",
                "required": True,
                "present": False,
            }
        else:
            source = "environment" if self.env_settings.s3_bucket_name == self.s3_bucket_name else "database"
            details["s3_bucket_name"] = {"name": "S3 Bucket Name", "source": source, "required": True, "present": True}

        return {"is_complete": len(missing_settings) == 0, "missing_settings": missing_settings, "details": details}

    async def is_initialization_complete(self) -> bool:
        """Quick check if initialization is complete."""
        status = await self.get_initialization_status()
        return status["is_complete"]


class SettingsAdapter:
    """Adapter to make SettingsService compatible with existing Settings interface."""

    def __init__(self, settings_service: SettingsService):
        self.settings_service = settings_service

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to SettingsService."""
        if hasattr(self.settings_service, name):
            return getattr(self.settings_service, name)
        else:
            # Fallback to environment settings
            return getattr(self.settings_service.env_settings, name)
