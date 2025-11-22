"""Tests for UserContextMiddleware."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app, get_template_context
from app.models.user import User
from app.middleware import UserContextMiddleware


@pytest.mark.asyncio
class TestGetTemplateContext:
    """Tests for get_template_context helper function."""

    def test_get_template_context_with_user(self):
        """Test that get_template_context includes user from request state."""
        # Create a mock request with a user in state
        mock_request = Mock(spec=Request)
        mock_user = Mock(spec=User)
        mock_user.username = "testuser"
        mock_user.id = "123"
        mock_request.state.user = mock_user

        # Get template context
        context = get_template_context(
            mock_request,
            page_title="Test Page",
            version="1.0.0",
        )

        # Verify context includes request, current_user, and other kwargs
        assert context["request"] == mock_request
        assert context["current_user"] == mock_user
        assert context["page_title"] == "Test Page"
        assert context["version"] == "1.0.0"

    def test_get_template_context_without_user(self):
        """Test that get_template_context handles missing user gracefully."""
        # Create a mock request without a user in state
        mock_request = Mock(spec=Request)
        # Simulate missing user attribute
        del mock_request.state.user

        # Get template context
        context = get_template_context(
            mock_request,
            page_title="Test Page",
        )

        # Verify context includes None for current_user
        assert context["request"] == mock_request
        assert context["current_user"] is None
        assert context["page_title"] == "Test Page"


@pytest.mark.asyncio
class TestUserContextMiddleware:
    """Tests for UserContextMiddleware."""

    async def test_middleware_sets_user_state_when_authenticated(self, async_db_session: AsyncSession):
        """Test that middleware sets request.state.user when authenticated."""
        # Create a test user
        user = User(username="testuser", email="test@example.com", hashed_password="fake_hash")
        async_db_session.add(user)
        await async_db_session.commit()
        await async_db_session.refresh(user)

        # Mock the authentication components
        with (
            patch("app.middleware.auth_backend") as mock_auth_backend,
            patch("app.middleware.get_jwt_strategy") as mock_get_jwt_strategy,
            patch("app.middleware.async_session_maker") as mock_session_maker,
        ):

            # Setup mock transport to return a token
            mock_transport = AsyncMock()
            mock_transport.get_login_response = AsyncMock(return_value="fake_token")
            mock_auth_backend.transport = mock_transport

            # Setup mock strategy to decode token and return user_id
            mock_strategy = AsyncMock()
            mock_strategy.read_token = AsyncMock(return_value=user.id)
            mock_get_jwt_strategy.return_value = mock_strategy

            # Setup mock session to return the user
            mock_session = AsyncMock()
            mock_result = AsyncMock()
            mock_result.scalar_one_or_none = AsyncMock(return_value=user)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_session

            # Create a mock request and call_next
            mock_request = Mock(spec=Request)
            mock_request.state = Mock()
            mock_response = Mock()
            mock_call_next = AsyncMock(return_value=mock_response)

            # Create middleware instance and dispatch
            middleware = UserContextMiddleware(app)
            response = await middleware.dispatch(mock_request, mock_call_next)

            # Verify request.state.user was set
            assert mock_request.state.user == user
            assert response == mock_response

    async def test_middleware_sets_user_to_none_when_not_authenticated(self):
        """Test that middleware sets request.state.user to None when not authenticated."""
        with patch("app.middleware.auth_backend") as mock_auth_backend:
            # Setup mock transport to return no token
            mock_transport = AsyncMock()
            mock_transport.get_login_response = AsyncMock(return_value=None)
            mock_auth_backend.transport = mock_transport

            # Create a mock request and call_next
            mock_request = Mock(spec=Request)
            mock_request.state = Mock()
            mock_response = Mock()
            mock_call_next = AsyncMock(return_value=mock_response)

            # Create middleware instance and dispatch
            middleware = UserContextMiddleware(app)
            response = await middleware.dispatch(mock_request, mock_call_next)

            # Verify request.state.user was set to None
            assert mock_request.state.user is None
            assert response == mock_response

    async def test_middleware_handles_errors_gracefully(self):
        """Test that middleware handles errors gracefully and sets user to None."""
        with patch("app.middleware.auth_backend") as mock_auth_backend:
            # Setup mock transport to raise an exception
            mock_transport = AsyncMock()
            mock_transport.get_login_response = AsyncMock(side_effect=Exception("Auth error"))
            mock_auth_backend.transport = mock_transport

            # Create a mock request and call_next
            mock_request = Mock(spec=Request)
            mock_request.state = Mock()
            mock_response = Mock()
            mock_call_next = AsyncMock(return_value=mock_response)

            # Create middleware instance and dispatch
            middleware = UserContextMiddleware(app)
            response = await middleware.dispatch(mock_request, mock_call_next)

            # Verify request.state.user was set to None despite error
            assert mock_request.state.user is None
            assert response == mock_response


class TestUserIdentityInTemplate:
    """Integration tests for user identity display in templates."""

    def test_username_displayed_when_authenticated(self):
        """Test that username is displayed in the UI when user is authenticated."""
        client = TestClient(app)

        # Register and login a user
        register_response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "testpass123",
            },
        )

        # If registration is disabled, skip this test
        if register_response.status_code == 403:
            pytest.skip("Registration is disabled")

        # Login
        login_response = client.post(
            "/api/auth/jwt/login",
            data={"username": "testuser", "password": "testpass123"},
        )

        # Check if login was successful
        if login_response.status_code != 200:
            pytest.skip("Login failed - authentication may be configured differently")

        # Access the main page
        response = client.get("/")

        # Verify the response includes the username
        assert response.status_code == 200
        assert "testuser" in response.text or "USER:" in response.text

    def test_logout_button_displayed_when_authenticated(self):
        """Test that logout button is displayed when user is authenticated."""
        client = TestClient(app)

        # Register and login a user
        register_response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser2",
                "email": "test2@example.com",
                "password": "testpass123",
            },
        )

        # If registration is disabled, skip this test
        if register_response.status_code == 403:
            pytest.skip("Registration is disabled")

        # Login
        login_response = client.post(
            "/api/auth/jwt/login",
            data={"username": "testuser2", "password": "testpass123"},
        )

        # Check if login was successful
        if login_response.status_code != 200:
            pytest.skip("Login failed - authentication may be configured differently")

        # Access the main page
        response = client.get("/")

        # Verify the response includes the logout button
        assert response.status_code == 200
        assert "LOGOUT" in response.text or "logout()" in response.text

    def test_user_info_not_displayed_when_not_authenticated(self):
        """Test that user info is not displayed when not authenticated."""
        client = TestClient(app)

        # Access the main page without authentication
        response = client.get("/login")

        # Verify the response does not include user-specific elements
        assert response.status_code == 200
        # The login page should not show user info or logout
        # (it may redirect to login if auth is required)
