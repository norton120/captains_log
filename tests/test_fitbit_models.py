"""Tests for Fitbit-related database models."""

from datetime import datetime, timedelta, UTC
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.settings import UserPreferences
from app.models.fitbit import UserFitbitSettings, FitbitData
from app.models.log_entry import LogEntry
from app.models.user import User


@pytest.mark.asyncio
class TestUserPreferencesFitbitFields:
    """Test that UserPreferences model has Fitbit OAuth fields."""

    async def test_user_preferences_fitbit_fields_exist(self, async_db_session: AsyncSession):
        """Verify UserPreferences model has new Fitbit OAuth fields."""
        # Create a UserPreferences instance with Fitbit fields
        prefs = UserPreferences(
            id=uuid.uuid4(),
            fitbit_oauth_client_id="test_client_id",
            fitbit_oauth_client_secret="test_client_secret",
        )
        async_db_session.add(prefs)
        await async_db_session.commit()

        # Retrieve and verify
        result = await async_db_session.execute(select(UserPreferences).where(UserPreferences.id == prefs.id))
        retrieved = result.scalar_one()

        assert retrieved.fitbit_oauth_client_id == "test_client_id"
        assert retrieved.fitbit_oauth_client_secret == "test_client_secret"

    async def test_user_preferences_fitbit_fields_nullable(self, async_db_session: AsyncSession):
        """Verify Fitbit fields are nullable."""
        prefs = UserPreferences(id=uuid.uuid4())
        async_db_session.add(prefs)
        await async_db_session.commit()

        result = await async_db_session.execute(select(UserPreferences).where(UserPreferences.id == prefs.id))
        retrieved = result.scalar_one()

        assert retrieved.fitbit_oauth_client_id is None
        assert retrieved.fitbit_oauth_client_secret is None


@pytest.mark.asyncio
class TestUserFitbitSettingsModel:
    """Test UserFitbitSettings model (user-specific Fitbit configuration)."""

    async def test_user_fitbit_settings_model_creation(self, async_db_session: AsyncSession, test_user: User):
        """Test creating a UserFitbitSettings instance."""
        expires_at = datetime.now(UTC) + timedelta(hours=8)
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_user_id="FITBIT123",
            fitbit_device_id="DEVICE456",
            access_token="access_token_abc",
            refresh_token="refresh_token_xyz",
            token_expires_at=expires_at,
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Retrieve and verify
        result = await async_db_session.execute(select(UserFitbitSettings).where(UserFitbitSettings.id == settings.id))
        retrieved = result.scalar_one()

        assert retrieved.user_id == test_user.id
        assert retrieved.fitbit_user_id == "FITBIT123"
        assert retrieved.fitbit_device_id == "DEVICE456"
        assert retrieved.access_token == "access_token_abc"
        assert retrieved.refresh_token == "refresh_token_xyz"
        assert retrieved.token_expires_at == expires_at
        assert retrieved.is_authorized is True
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    async def test_user_fitbit_settings_unique_user_constraint(self, async_db_session: AsyncSession, test_user: User):
        """Test that user_id must be unique (one Fitbit config per user)."""
        settings1 = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=False,
        )
        async_db_session.add(settings1)
        await async_db_session.commit()

        # Try to create another settings for the same user
        settings2 = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=False,
        )
        async_db_session.add(settings2)

        with pytest.raises(IntegrityError):
            await async_db_session.commit()

    async def test_user_fitbit_settings_nullable_fields(self, async_db_session: AsyncSession, test_user: User):
        """Test that Fitbit token fields are nullable."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=False,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        result = await async_db_session.execute(select(UserFitbitSettings).where(UserFitbitSettings.id == settings.id))
        retrieved = result.scalar_one()

        assert retrieved.fitbit_user_id is None
        assert retrieved.fitbit_device_id is None
        assert retrieved.access_token is None
        assert retrieved.refresh_token is None
        assert retrieved.token_expires_at is None
        assert retrieved.is_authorized is False

    async def test_user_fitbit_settings_relationship_to_user(self, async_db_session: AsyncSession, test_user: User):
        """Test relationship between UserFitbitSettings and User."""
        from sqlalchemy.inspection import inspect

        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Reload and verify user_id is set correctly
        result = await async_db_session.execute(
            select(UserFitbitSettings).where(UserFitbitSettings.user_id == test_user.id)
        )
        settings = result.scalar_one()

        assert settings.user_id == test_user.id

        # Verify the relationship is defined in the model (without triggering lazy load)
        mapper = inspect(UserFitbitSettings)
        assert "user" in mapper.relationships.keys()


@pytest.mark.asyncio
class TestFitbitDataModel:
    """Test FitbitData model linked to log entries."""

    async def test_fitbit_data_model_creation(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
    ):
        """Test creating a FitbitData instance with all fields."""
        # Create a log entry first
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Create Fitbit data
        captured_at = datetime.now(UTC)
        fitbit_data = FitbitData(
            id=uuid.uuid4(),
            log_entry_id=log.id,
            user_id=test_user.id,
            captured_at=captured_at,
            heart_rate_bpm=72,
            resting_heart_rate_bpm=58,
            sleep_score=85,
            sleep_duration_minutes=450,
            sleep_efficiency_pct=92.5,
            blood_oxygen_pct=98.5,
            steps_today=8432,
            calories_burned_today=2145,
            active_minutes_today=45,
            distance_today_miles=4.2,
            floors_climbed_today=12,
            vo2_max=42.5,
            cardio_fitness_score=75,
            stress_score=35,
        )
        async_db_session.add(fitbit_data)
        await async_db_session.commit()

        # Retrieve and verify
        result = await async_db_session.execute(select(FitbitData).where(FitbitData.id == fitbit_data.id))
        retrieved = result.scalar_one()

        assert retrieved.log_entry_id == log.id
        assert retrieved.user_id == test_user.id
        assert retrieved.captured_at == captured_at
        assert retrieved.heart_rate_bpm == 72
        assert retrieved.resting_heart_rate_bpm == 58
        assert retrieved.sleep_score == 85
        assert retrieved.sleep_duration_minutes == 450
        assert retrieved.sleep_efficiency_pct == 92.5
        assert retrieved.blood_oxygen_pct == 98.5
        assert retrieved.steps_today == 8432
        assert retrieved.calories_burned_today == 2145
        assert retrieved.active_minutes_today == 45
        assert retrieved.distance_today_miles == 4.2
        assert retrieved.floors_climbed_today == 12
        assert retrieved.vo2_max == 42.5
        assert retrieved.cardio_fitness_score == 75
        assert retrieved.stress_score == 35

    async def test_fitbit_data_nullable_fields(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
    ):
        """Test that health metric fields are nullable."""
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Create Fitbit data with minimal fields
        fitbit_data = FitbitData(
            id=uuid.uuid4(),
            log_entry_id=log.id,
            user_id=test_user.id,
            captured_at=datetime.now(UTC),
        )
        async_db_session.add(fitbit_data)
        await async_db_session.commit()

        result = await async_db_session.execute(select(FitbitData).where(FitbitData.id == fitbit_data.id))
        retrieved = result.scalar_one()

        # All health metrics should be None
        assert retrieved.heart_rate_bpm is None
        assert retrieved.resting_heart_rate_bpm is None
        assert retrieved.sleep_score is None
        assert retrieved.blood_oxygen_pct is None
        assert retrieved.steps_today is None

    async def test_fitbit_data_unique_log_entry_constraint(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
    ):
        """Test that log_entry_id must be unique (one Fitbit data per log)."""
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        fitbit_data1 = FitbitData(
            id=uuid.uuid4(),
            log_entry_id=log.id,
            user_id=test_user.id,
            captured_at=datetime.now(UTC),
        )
        async_db_session.add(fitbit_data1)
        await async_db_session.commit()

        # Try to create another Fitbit data for the same log
        fitbit_data2 = FitbitData(
            id=uuid.uuid4(),
            log_entry_id=log.id,
            user_id=test_user.id,
            captured_at=datetime.now(UTC),
        )
        async_db_session.add(fitbit_data2)

        with pytest.raises(IntegrityError):
            await async_db_session.commit()


@pytest.mark.asyncio
class TestLogEntryFitbitRelationship:
    """Test relationship between LogEntry and FitbitData."""

    async def test_log_entry_fitbit_relationship(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
    ):
        """Verify LogEntry has relationship to FitbitData."""
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        fitbit_data = FitbitData(
            id=uuid.uuid4(),
            log_entry_id=log.id,
            user_id=test_user.id,
            captured_at=datetime.now(UTC),
            heart_rate_bpm=75,
        )
        async_db_session.add(fitbit_data)
        await async_db_session.commit()

        # Access relationship from log to fitbit_data
        await async_db_session.refresh(log, ["fitbit_data"])
        assert log.fitbit_data is not None
        assert log.fitbit_data.heart_rate_bpm == 75

        # Access relationship from fitbit_data to log
        await async_db_session.refresh(fitbit_data, ["log_entry"])
        assert fitbit_data.log_entry.id == log.id

    async def test_log_entry_without_fitbit_data(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
    ):
        """Test that logs can exist without Fitbit data."""
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        await async_db_session.refresh(log, ["fitbit_data"])
        assert log.fitbit_data is None
