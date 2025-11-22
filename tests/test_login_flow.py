"""Test login flow and authentication."""

import pytest
from httpx import AsyncClient
from fastapi import status

from app.models.user import User


@pytest.mark.asyncio
class TestLoginFlow:
    """Test login flow with successful authentication."""

    async def test_login_succeeds_and_redirects_to_home(self, api_client: AsyncClient, test_user: User):
        """Test that successful login redirects to the home page."""
        # Get the login page first to establish session
        response = await api_client.get("/login")
        assert response.status_code == status.HTTP_200_OK

        # Submit login credentials
        login_response = await api_client.post(
            "/api/auth/jwt/login",
            data={"username": test_user.email, "password": "password123"},
            follow_redirects=False,
        )
        assert login_response.status_code == status.HTTP_204_NO_CONTENT

        # Verify that cookie was set
        assert "fastapiusersauth" in login_response.cookies

        # Now try to access the home page - should work
        home_response = await api_client.get("/", follow_redirects=False)

        # Should not redirect to login anymore
        assert home_response.status_code != status.HTTP_302_FOUND
        if home_response.status_code == status.HTTP_302_FOUND:
            # If it does redirect, print where it's redirecting to
            print(f"Redirecting to: {home_response.headers.get('location')}")
            assert False, "Should not redirect after successful login"

    async def test_unauthenticated_access_redirects_to_login(self, api_client: AsyncClient):
        """Test that unauthenticated users are redirected to login."""
        response = await api_client.get("/", follow_redirects=False)
        assert response.status_code == status.HTTP_302_FOUND
        assert response.headers["location"].startswith("/login")
