"""Test that Fitbit credentials can be saved and retrieved via the settings API."""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app


@pytest.mark.asyncio
async def test_fitbit_credentials_can_be_saved_and_retrieved(
    async_db_session: AsyncSession,
):
    """Test that Fitbit OAuth credentials can be saved and retrieved via API."""

    # Create an HTTP client for the app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Update preferences with Fitbit credentials
        update_response = await client.put(
            "/api/settings/preferences",
            json={
                "fitbit_oauth_client_id": "test_client_id_123",
                "fitbit_oauth_client_secret": "test_client_secret_456",
            },
        )

        assert update_response.status_code == 200
        update_data = update_response.json()

        # Verify the response contains the saved credentials
        assert update_data["fitbit_oauth_client_id"] == "test_client_id_123"
        assert update_data["fitbit_oauth_client_secret"] == "test_client_secret_456"

        # Retrieve preferences to confirm they were persisted
        get_response = await client.get("/api/settings/preferences")

        assert get_response.status_code == 200
        get_data = get_response.json()

        # Verify the credentials were persisted
        assert get_data["fitbit_oauth_client_id"] == "test_client_id_123"
        assert get_data["fitbit_oauth_client_secret"] == "test_client_secret_456"


@pytest.mark.asyncio
async def test_fitbit_credentials_can_be_cleared(
    async_db_session: AsyncSession,
):
    """Test that Fitbit OAuth credentials can be cleared (set to null)."""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First, set some credentials
        await client.put(
            "/api/settings/preferences",
            json={
                "fitbit_oauth_client_id": "test_client_id",
                "fitbit_oauth_client_secret": "test_client_secret",
            },
        )

        # Now clear them by sending null
        clear_response = await client.put(
            "/api/settings/preferences",
            json={
                "fitbit_oauth_client_id": None,
                "fitbit_oauth_client_secret": None,
            },
        )

        assert clear_response.status_code == 200
        clear_data = clear_response.json()

        # Verify the credentials were cleared
        assert clear_data["fitbit_oauth_client_id"] is None
        assert clear_data["fitbit_oauth_client_secret"] is None
