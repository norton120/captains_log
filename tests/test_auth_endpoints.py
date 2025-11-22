"""Tests for authentication endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestAuthEndpoints:
    """Test authentication API endpoints."""

    def test_logout_endpoint_success(self):
        """Test that logout endpoint works correctly for authenticated users."""
        client = TestClient(app)

        # First, register a test user
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "logout_test@example.com",
                "username": "logout_testuser",
                "password": "testpassword123",
            },
        )

        # Login might fail if registration is disabled, so we skip if 403
        if register_response.status_code == 403:
            pytest.skip("User registration is disabled")

        assert register_response.status_code == 201

        # Login with the test user
        login_response = client.post(
            "/api/auth/jwt/login",
            data={
                "username": "logout_testuser",
                "password": "testpassword123",
            },
        )

        assert login_response.status_code == 204
        assert "captains_log_session" in login_response.cookies

        # Get the session cookie
        cookies = login_response.cookies

        # Now test logout
        logout_response = client.post(
            "/api/auth/jwt/logout",
            cookies=cookies,
        )

        # Verify logout succeeded
        assert logout_response.status_code == 204

        # Verify the cookie was cleared (should be empty or deleted)
        # FastAPI users typically sets max-age=0 to clear the cookie
        if "Set-Cookie" in logout_response.headers:
            # Cookie should be deleted or expired
            assert (
                "max-age=0" in logout_response.headers.get("Set-Cookie", "").lower()
                or logout_response.cookies.get("captains_log_session") is None
            )

    def test_logout_endpoint_unauthenticated(self):
        """Test that logout endpoint returns 401 for unauthenticated users."""
        client = TestClient(app)

        # Try to logout without being logged in
        logout_response = client.post("/api/auth/jwt/logout")

        # Should return 401 Unauthorized
        assert logout_response.status_code == 401

    def test_logout_endpoint_no_500_error(self):
        """Test that logout endpoint does not return 503 Service Unavailable.

        This is a regression test for the bug where logout was calling
        auth_backend.get_logout_response() which doesn't exist.
        """
        client = TestClient(app)

        # Register and login a test user
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "regression_test@example.com",
                "username": "regression_testuser",
                "password": "testpassword123",
            },
        )

        if register_response.status_code == 403:
            pytest.skip("User registration is disabled")

        assert register_response.status_code == 201

        login_response = client.post(
            "/api/auth/jwt/login",
            data={
                "username": "regression_testuser",
                "password": "testpassword123",
            },
        )

        assert login_response.status_code == 204

        # Test logout - should NOT return 503
        logout_response = client.post(
            "/api/auth/jwt/logout",
            cookies=login_response.cookies,
        )

        # Verify we don't get 503 Service Unavailable
        assert logout_response.status_code != 503
        # Should be 204 No Content on success
        assert logout_response.status_code == 204
