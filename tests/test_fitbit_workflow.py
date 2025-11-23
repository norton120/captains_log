"""Tests for Fitbit workflow integration with log processing."""
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.log_entry import LogEntry, ProcessingStatus
from app.models.fitbit import UserFitbitSettings, FitbitData
from app.workflows.audio_processor import AudioProcessingWorkflow


@pytest.fixture
def user_with_fitbit(test_user: User, async_db_session: AsyncSession):
    """Create a user with Fitbit authorized."""

    async def _create():
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_user_id="FITBIT123",
            fitbit_device_id="DEVICE456",
            access_token="valid_access_token",
            refresh_token="valid_refresh_token",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()
        return test_user

    return _create


@pytest.mark.asyncio
class TestFitbitDataCaptureOnLogSave:
    """Test Fitbit data capture when log is saved."""

    async def test_capture_fitbit_data_on_log_save(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test that Fitbit data is captured when log is saved."""
        # Create user with Fitbit
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        # Create log entry
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Mock Fitbit service
        with patch("app.workflows.process_audio.FitbitService") as mock_fitbit_service:
            mock_fitbit_service.return_value.get_comprehensive_health_snapshot = AsyncMock(
                return_value={
                    "heart_rate_bpm": 72,
                    "resting_heart_rate_bpm": 58,
                    "sleep_score": 85,
                    "sleep_duration_minutes": 450,
                    "sleep_efficiency_pct": 92.5,
                    "blood_oxygen_pct": 98.5,
                    "steps_today": 8432,
                    "calories_burned_today": 2145,
                    "active_minutes_today": 45,
                    "distance_today_miles": 4.2,
                    "floors_climbed_today": 12,
                }
            )

            # Process the audio (which should trigger Fitbit capture)
            await process_audio_workflow(log.id, async_db_session)

        # Verify FitbitData was created
        result = await async_db_session.execute(
            select(FitbitData).where(FitbitData.log_entry_id == log.id)
        )
        fitbit_data = result.scalar_one()

        assert fitbit_data is not None
        assert fitbit_data.user_id == test_user.id
        assert fitbit_data.heart_rate_bpm == 72
        assert fitbit_data.sleep_score == 85
        assert fitbit_data.steps_today == 8432
        assert fitbit_data.blood_oxygen_pct == 98.5
        assert fitbit_data.captured_at is not None

    async def test_fitbit_capture_skipped_if_not_authorized(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test that Fitbit capture is skipped for users without Fitbit connection."""
        # Create log entry (user has no Fitbit settings)
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Process the audio
        await process_audio_workflow(log.id, async_db_session)

        # Verify NO FitbitData was created
        result = await async_db_session.execute(
            select(FitbitData).where(FitbitData.log_entry_id == log.id)
        )
        fitbit_data = result.scalar_one_or_none()

        assert fitbit_data is None

        # Verify log processing still completed successfully
        await async_db_session.refresh(log)
        assert log.processing_status == ProcessingStatus.COMPLETED

    async def test_fitbit_capture_handles_api_failures(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test that log processing continues when Fitbit API fails."""
        # Create user with Fitbit
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)

        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Mock Fitbit service to raise an error
        with patch("app.workflows.process_audio.FitbitService") as mock_fitbit_service:
            mock_fitbit_service.return_value.get_comprehensive_health_snapshot = AsyncMock(
                side_effect=Exception("Fitbit API unavailable")
            )

            # Process should not fail
            await process_audio_workflow(log.id, async_db_session)

        # Verify log processing completed despite Fitbit failure
        await async_db_session.refresh(log)
        assert log.processing_status == ProcessingStatus.COMPLETED

        # Verify NO FitbitData was created
        result = await async_db_session.execute(
            select(FitbitData).where(FitbitData.log_entry_id == log.id)
        )
        fitbit_data = result.scalar_one_or_none()
        assert fitbit_data is None

    async def test_fitbit_data_captured_after_transcription(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test that Fitbit data is captured after transcription but before vectorization."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)

        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Track workflow order
        call_order = []

        async def mock_transcribe(*args, **kwargs):
            call_order.append("transcribe")
            return "Test transcription"

        async def mock_fitbit_capture(*args, **kwargs):
            call_order.append("fitbit")
            return {
                "heart_rate_bpm": 72,
            }

        async def mock_embed(*args, **kwargs):
            call_order.append("embed")
            return [0.1] * 1536

        with patch("app.workflows.process_audio.FitbitService") as mock_fitbit_service:
            mock_fitbit_service.return_value.get_comprehensive_health_snapshot = mock_fitbit_capture
            mock_async_openai_client.audio.transcriptions.create = mock_transcribe
            mock_async_openai_client.embeddings.create = mock_embed

            await process_audio_workflow(log.id, async_db_session)

        # Verify order: transcribe -> fitbit -> embed
        assert call_order.index("transcribe") < call_order.index("fitbit")
        assert call_order.index("fitbit") < call_order.index("embed")

    async def test_fitbit_captured_at_timestamp_accuracy(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test that captured_at timestamp is accurate."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)

        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log)
        await async_db_session.commit()

        before_capture = datetime.now(UTC)

        with patch("app.workflows.process_audio.FitbitService") as mock_fitbit_service:
            mock_fitbit_service.return_value.get_comprehensive_health_snapshot = AsyncMock(
                return_value={"heart_rate_bpm": 72}
            )

            await process_audio_workflow(log.id, async_db_session)

        after_capture = datetime.now(UTC)

        # Verify timestamp
        result = await async_db_session.execute(
            select(FitbitData).where(FitbitData.log_entry_id == log.id)
        )
        fitbit_data = result.scalar_one()

        assert before_capture <= fitbit_data.captured_at <= after_capture


@pytest.mark.asyncio
class TestFitbitDataWithPartialMetrics:
    """Test Fitbit data capture with partial/missing metrics."""

    async def test_fitbit_capture_with_partial_metrics(
        self,
        async_db_session: AsyncSession,
        test_user: User,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test capturing Fitbit data when only some metrics are available."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)

        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log)
        await async_db_session.commit()

        # Mock Fitbit with only heart rate (no sleep, no activity)
        with patch("app.workflows.process_audio.FitbitService") as mock_fitbit_service:
            mock_fitbit_service.return_value.get_comprehensive_health_snapshot = AsyncMock(
                return_value={
                    "heart_rate_bpm": 72,
                    "resting_heart_rate_bpm": 58,
                    # No sleep data
                    # No activity data
                }
            )

            await process_audio_workflow(log.id, async_db_session)

        # Verify FitbitData created with partial data
        result = await async_db_session.execute(
            select(FitbitData).where(FitbitData.log_entry_id == log.id)
        )
        fitbit_data = result.scalar_one()

        assert fitbit_data.heart_rate_bpm == 72
        assert fitbit_data.resting_heart_rate_bpm == 58
        assert fitbit_data.sleep_score is None
        assert fitbit_data.steps_today is None


@pytest.mark.asyncio
class TestFitbitCaptureUserIsolation:
    """Test that Fitbit data is properly isolated per user."""

    async def test_fitbit_data_uses_correct_user_token(
        self,
        async_db_session: AsyncSession,
        sample_audio_file,
        mock_async_openai_client,
        mock_s3_service,
    ):
        """Test that each user's Fitbit token is used for their logs."""
        from app.models.user import User

        # Create two users with different Fitbit settings
        user1 = User(
            id=uuid.uuid4(),
            email="user1@example.com",
            hashed_password="hash1",
            is_active=True,
        )
        user2 = User(
            id=uuid.uuid4(),
            email="user2@example.com",
            hashed_password="hash2",
            is_active=True,
        )
        async_db_session.add_all([user1, user2])

        settings1 = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=user1.id,
            access_token="user1_token",
            is_authorized=True,
        )
        settings2 = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=user2.id,
            access_token="user2_token",
            is_authorized=True,
        )
        async_db_session.add_all([settings1, settings2])

        log1 = LogEntry(
            id=uuid.uuid4(),
            user_id=user1.id,
            original_filename="test1.wav",
            audio_local_path=str(sample_audio_file),
            processing_status=ProcessingStatus.PENDING,
        )
        async_db_session.add(log1)
        await async_db_session.commit()

        captured_token = None

        async def mock_capture(access_token):
            nonlocal captured_token
            captured_token = access_token
            return {"heart_rate_bpm": 70}

        with patch("app.workflows.process_audio.FitbitService") as mock_fitbit_service:
            mock_fitbit_service.return_value.get_comprehensive_health_snapshot = mock_capture

            await process_audio_workflow(log1.id, async_db_session)

        # Verify user1's token was used
        assert captured_token == "user1_token"
