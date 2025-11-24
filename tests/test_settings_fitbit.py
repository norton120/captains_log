"""Tests for Fitbit settings integration."""

from datetime import datetime, timedelta, UTC
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.fitbit import UserFitbitSettings
from app.models.settings import UserPreferences
from app.config import Settings


@pytest.mark.asyncio
class TestSettingsServiceFitbitOAuth:
    """Test SettingsService exposes Fitbit OAuth credentials."""

    async def test_settings_service_exposes_fitbit_oauth_credentials(self, test_settings: Settings):
        """Test that SettingsService has Fitbit OAuth properties."""
        assert hasattr(test_settings, "fitbit_oauth_client_id")
        assert hasattr(test_settings, "fitbit_oauth_client_secret")

    async def test_settings_fitbit_oauth_from_environment(self, monkeypatch):
        """Test Fitbit OAuth credentials loaded from environment."""
        monkeypatch.setenv("FITBIT_OAUTH_CLIENT_ID", "env_client_id")
        monkeypatch.setenv("FITBIT_OAUTH_CLIENT_SECRET", "env_client_secret")

        settings = Settings()

        assert settings.fitbit_oauth_client_id == "env_client_id"
        assert settings.fitbit_oauth_client_secret == "env_client_secret"

    async def test_settings_fitbit_oauth_from_database(self, async_db_session: AsyncSession):
        """Test Fitbit OAuth credentials loaded from database."""
        # Create UserPreferences with Fitbit OAuth credentials
        prefs = UserPreferences(
            id=uuid.uuid4(),
            fitbit_oauth_client_id="db_client_id",
            fitbit_oauth_client_secret="db_client_secret",
        )
        async_db_session.add(prefs)
        await async_db_session.commit()

        from app.config import SettingsService

        settings_service = SettingsService(async_db_session)
        await settings_service.load_preferences()

        assert settings_service.fitbit_oauth_client_id == "db_client_id"
        assert settings_service.fitbit_oauth_client_secret == "db_client_secret"

    async def test_settings_fitbit_oauth_database_overrides_env(self, async_db_session: AsyncSession, monkeypatch):
        """Test that database Fitbit OAuth credentials override environment."""
        monkeypatch.setenv("FITBIT_OAUTH_CLIENT_ID", "env_client_id")

        prefs = UserPreferences(
            id=uuid.uuid4(),
            fitbit_oauth_client_id="db_client_id",
        )
        async_db_session.add(prefs)
        await async_db_session.commit()

        from app.config import SettingsService

        settings_service = SettingsService(async_db_session)
        await settings_service.load_preferences()

        # Database should override environment
        assert settings_service.fitbit_oauth_client_id == "db_client_id"


@pytest.mark.asyncio
class TestUserFitbitSettingsCRUD:
    """Test CRUD operations on UserFitbitSettings."""

    async def test_create_user_fitbit_settings(self, async_db_session: AsyncSession, test_user: User):
        """Test creating UserFitbitSettings."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_user_id="FITBIT123",
            access_token="access_token",
            refresh_token="refresh_token",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Retrieve
        result = await async_db_session.execute(
            select(UserFitbitSettings).where(UserFitbitSettings.user_id == test_user.id)
        )
        retrieved = result.scalar_one()

        assert retrieved.fitbit_user_id == "FITBIT123"
        assert retrieved.is_authorized is True

    async def test_read_user_fitbit_settings(self, async_db_session: AsyncSession, test_user: User):
        """Test reading UserFitbitSettings."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_device_id="DEVICE456",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Read
        result = await async_db_session.execute(
            select(UserFitbitSettings).where(UserFitbitSettings.user_id == test_user.id)
        )
        retrieved = result.scalar_one()

        assert retrieved.user_id == test_user.id
        assert retrieved.fitbit_device_id == "DEVICE456"

    async def test_update_user_fitbit_settings(self, async_db_session: AsyncSession, test_user: User):
        """Test updating UserFitbitSettings."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_device_id="OLD_DEVICE",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Update
        settings.fitbit_device_id = "NEW_DEVICE"
        settings.access_token = "new_token"
        await async_db_session.commit()

        # Verify
        await async_db_session.refresh(settings)
        assert settings.fitbit_device_id == "NEW_DEVICE"
        assert settings.access_token == "new_token"

    async def test_delete_user_fitbit_settings(self, async_db_session: AsyncSession, test_user: User):
        """Test deleting UserFitbitSettings."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Delete
        await async_db_session.delete(settings)
        await async_db_session.commit()

        # Verify deletion
        result = await async_db_session.execute(
            select(UserFitbitSettings).where(UserFitbitSettings.user_id == test_user.id)
        )
        retrieved = result.scalar_one_or_none()

        assert retrieved is None

    async def test_unique_user_constraint_enforced(self, async_db_session: AsyncSession, test_user: User):
        """Test that unique constraint on user_id is enforced."""
        from sqlalchemy.exc import IntegrityError

        settings1 = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=True,
        )
        async_db_session.add(settings1)
        await async_db_session.commit()

        # Try to create another settings for same user
        settings2 = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=False,
        )
        async_db_session.add(settings2)

        with pytest.raises(IntegrityError):
            await async_db_session.commit()


@pytest.mark.asyncio
class TestUserFitbitSettingsHelpers:
    """Test helper methods for UserFitbitSettings."""

    async def test_is_token_expired_true(self, async_db_session: AsyncSession, test_user: User):
        """Test is_token_expired returns True for expired token."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            token_expires_at=datetime.now(UTC) - timedelta(hours=1),
            is_authorized=True,
        )

        assert settings.is_token_expired() is True

    async def test_is_token_expired_false(self, async_db_session: AsyncSession, test_user: User):
        """Test is_token_expired returns False for valid token."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            token_expires_at=datetime.now(UTC) + timedelta(hours=8),
            is_authorized=True,
        )

        assert settings.is_token_expired() is False

    async def test_is_token_expired_no_expiry(self, async_db_session: AsyncSession, test_user: User):
        """Test is_token_expired when no expiry set."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            token_expires_at=None,
            is_authorized=True,
        )

        # Should be considered expired if no expiry date
        assert settings.is_token_expired() is True

    async def test_clear_tokens(self, async_db_session: AsyncSession, test_user: User):
        """Test clear_tokens helper method."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_user_id="FITBIT123",
            fitbit_device_id="DEVICE456",
            access_token="token",
            refresh_token="refresh",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Clear tokens
        settings.clear_tokens()
        await async_db_session.commit()

        await async_db_session.refresh(settings)
        assert settings.access_token is None
        assert settings.refresh_token is None
        assert settings.fitbit_user_id is None
        assert settings.fitbit_device_id is None
        assert settings.is_authorized is False
