"""Tests for User model and authentication."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
class TestUserModel:
    """Tests for the User model."""

    async def test_create_user(self, async_db_session: AsyncSession):
        """Test creating a user."""
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.created_at is not None

    async def test_user_unique_username(self, async_db_session: AsyncSession):
        """Test that usernames must be unique."""
        user1 = User(username="testuser", email="test1@example.com")
        async_db_session.add(user1)
        await async_db_session.commit()

        # Attempt to create another user with same username
        user2 = User(username="testuser", email="test2@example.com")
        async_db_session.add(user2)

        with pytest.raises(Exception):  # Should raise IntegrityError
            await async_db_session.commit()

    async def test_user_unique_email(self, async_db_session: AsyncSession):
        """Test that emails must be unique."""
        user1 = User(username="testuser1", email="test@example.com")
        async_db_session.add(user1)
        await async_db_session.commit()

        # Attempt to create another user with same email
        user2 = User(username="testuser2", email="test@example.com")
        async_db_session.add(user2)

        with pytest.raises(Exception):  # Should raise IntegrityError
            await async_db_session.commit()

    async def test_user_repr(self, async_db_session: AsyncSession):
        """Test User model string representation."""
        user = User(username="testuser", email="test@example.com")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        repr_str = repr(user)
        assert "User" in repr_str
        assert user.username in repr_str
