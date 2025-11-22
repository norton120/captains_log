"""Tests for LogEntry user foreign key relationship."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log_entry import LogEntry, ProcessingStatus
from app.models.user import User


@pytest.mark.asyncio
class TestLogEntryUserRelationship:
    """Tests for LogEntry and User relationship."""

    async def test_log_entry_requires_user_id(self, async_db_session: AsyncSession):
        """Test that LogEntry requires a user_id."""
        # Create a user first
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        # Create a log entry without user_id should fail
        log_entry = LogEntry(
            audio_s3_key="test/audio.wav",
            processing_status=ProcessingStatus.PENDING
        )
        async_db_session.add(log_entry)

        with pytest.raises(Exception):  # Should raise IntegrityError
            await async_db_session.commit()

    async def test_log_entry_with_user_id(self, async_db_session: AsyncSession):
        """Test creating a log entry with user_id."""
        # Create a user
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        # Create a log entry with user_id
        log_entry = LogEntry(
            user_id=user.id,
            audio_s3_key="test/audio.wav",
            processing_status=ProcessingStatus.PENDING
        )
        async_db_session.add(log_entry)
        await async_db_session.commit()
        await async_db_session.refresh(log_entry)

        assert log_entry.id is not None
        assert log_entry.user_id == user.id

    async def test_log_entry_user_relationship(self, async_db_session: AsyncSession):
        """Test the user relationship on LogEntry."""
        # Create a user
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        # Create a log entry
        log_entry = LogEntry(
            user_id=user.id,
            audio_s3_key="test/audio.wav",
            processing_status=ProcessingStatus.PENDING
        )
        async_db_session.add(log_entry)
        await async_db_session.commit()
        await async_db_session.refresh(log_entry)

        # Access the user via relationship
        result = await async_db_session.execute(
            select(LogEntry).where(LogEntry.id == log_entry.id)
        )
        fetched_entry = result.scalar_one()

        # Fetch the user relationship
        await async_db_session.refresh(fetched_entry, ["user"])
        assert fetched_entry.user is not None
        assert fetched_entry.user.id == user.id
        assert fetched_entry.user.username == "testuser"

    async def test_user_can_have_multiple_log_entries(self, async_db_session: AsyncSession):
        """Test that a user can have multiple log entries."""
        # Create a user
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        # Create multiple log entries for this user
        log_entry1 = LogEntry(
            user_id=user.id,
            audio_s3_key="test/audio1.wav",
            processing_status=ProcessingStatus.PENDING
        )
        log_entry2 = LogEntry(
            user_id=user.id,
            audio_s3_key="test/audio2.wav",
            processing_status=ProcessingStatus.COMPLETED
        )
        async_db_session.add_all([log_entry1, log_entry2])
        await async_db_session.commit()

        # Query all log entries for this user
        result = await async_db_session.execute(
            select(LogEntry).where(LogEntry.user_id == user.id)
        )
        user_logs = result.scalars().all()

        assert len(user_logs) == 2
        assert all(log.user_id == user.id for log in user_logs)

    async def test_delete_user_behavior(self, async_db_session: AsyncSession):
        """Test behavior when deleting a user (should be restricted)."""
        # Create a user
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        # Create a log entry
        log_entry = LogEntry(
            user_id=user.id,
            audio_s3_key="test/audio.wav",
            processing_status=ProcessingStatus.PENDING
        )
        async_db_session.add(log_entry)
        await async_db_session.commit()

        # Try to delete the user (should fail because of foreign key constraint)
        await async_db_session.delete(user)

        with pytest.raises(Exception):  # Should raise IntegrityError
            await async_db_session.commit()
