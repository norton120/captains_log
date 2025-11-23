"""Tests for Fitbit API endpoints."""
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from httpx import AsyncClient
from fastapi import status

from app.models.user import User
from app.models.fitbit import UserFitbitSettings


@pytest.mark.asyncio
class TestFitbitCallbackUrlEndpoint:
    """Test /api/fitbit/callback-url endpoint."""

    async def test_get_callback_url(self, api_client: AsyncClient):
        """Test that callback-url endpoint returns the correct callback URL."""
        response = await api_client.get("/api/fitbit/callback-url")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "callback_url" in data
        assert "/api/fitbit/callback" in data["callback_url"]


@pytest.mark.asyncio
class TestFitbitAuthorizeEndpoint:
    """Test /api/fitbit/authorize endpoint."""

    async def test_fitbit_authorize_endpoint_redirects(
        self, api_client: AsyncClient, test_user: User
    ):
        """Test that /api/fitbit/authorize redirects to Fitbit OAuth URL."""
        with patch("app.api.fitbit.FitbitService") as mock_service:
            mock_service.return_value.get_authorization_url.return_value = (
                "https://www.fitbit.com/oauth2/authorize?client_id=test"
            )

            response = await api_client.get(
                "/api/fitbit/authorize",
                follow_redirects=False,
            )

            assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
            assert "fitbit.com" in response.headers["location"]

    async def test_fitbit_authorize_requires_authentication(
        self, api_client: AsyncClient
    ):
        """Test that authorize endpoint requires authentication."""
        # Create a new client without authentication
        from app.main import app

        async with AsyncClient(app=app, base_url="http://test") as unauth_client:
            response = await unauth_client.get(
                "/api/fitbit/authorize",
                follow_redirects=False,
            )

            # Should redirect to login or return 401
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]


@pytest.mark.asyncio
class TestFitbitCallbackEndpoint:
    """Test /api/fitbit/callback endpoint."""

    async def test_fitbit_callback_endpoint_success(
        self, api_client: AsyncClient, test_user: User, async_db_session
    ):
        """Test /api/fitbit/callback with valid authorization code."""
        with patch("app.api.fitbit.FitbitService") as mock_service:
            mock_service.return_value.exchange_code_for_tokens = AsyncMock(
                return_value={
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token",
                    "fitbit_user_id": "FITBIT123",
                    "expires_at": datetime.now(UTC) + timedelta(hours=8),
                }
            )

            response = await api_client.get(
                "/api/fitbit/callback?code=auth_code_123&state=random_state",
                follow_redirects=False,
            )

            assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
            assert "/settings" in response.headers["location"]

    async def test_fitbit_callback_endpoint_with_error(
        self, api_client: AsyncClient, test_user: User
    ):
        """Test callback with error parameter from Fitbit."""
        response = await api_client.get(
            "/api/fitbit/callback?error=access_denied&error_description=User%20denied",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert "/settings" in response.headers["location"]
        # Error message should be in session or flash message

    async def test_fitbit_callback_missing_code(
        self, api_client: AsyncClient, test_user: User
    ):
        """Test callback without code or error parameter."""
        response = await api_client.get(
            "/api/fitbit/callback",
            follow_redirects=False,
        )

        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_307_TEMPORARY_REDIRECT,
        ]


@pytest.mark.asyncio
class TestFitbitDevicesEndpoint:
    """Test /api/fitbit/devices endpoint."""

    async def test_get_fitbit_devices_endpoint(
        self, api_client: AsyncClient, test_user: User, async_db_session
    ):
        """Test fetching user's Fitbit devices."""
        # Create user Fitbit settings
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        with patch("app.api.fitbit.FitbitService") as mock_service:
            mock_service.return_value.get_user_devices = AsyncMock(
                return_value=[
                    {
                        "id": "DEVICE123",
                        "deviceVersion": "Charge 5",
                        "type": "TRACKER",
                        "batteryLevel": 75,
                    }
                ]
            )

            response = await api_client.get("/api/fitbit/devices")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "DEVICE123"

    async def test_get_fitbit_devices_not_authorized(
        self, api_client: AsyncClient, test_user: User
    ):
        """Test devices endpoint when user hasn't authorized Fitbit."""
        response = await api_client.get("/api/fitbit/devices")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not authorized" in response.json()["detail"].lower()

    async def test_get_fitbit_devices_requires_authentication(self, api_client: AsyncClient):
        """Test devices endpoint requires authentication."""
        from app.main import app

        async with AsyncClient(app=app, base_url="http://test") as unauth_client:
            response = await unauth_client.get("/api/fitbit/devices")

            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]


@pytest.mark.asyncio
class TestSelectFitbitDeviceEndpoint:
    """Test /api/fitbit/device/select endpoint."""

    async def test_select_fitbit_device_endpoint(
        self, api_client: AsyncClient, test_user: User, async_db_session
    ):
        """Test selecting a Fitbit device."""
        # Create user Fitbit settings
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        response = await api_client.post(
            "/api/fitbit/device/select",
            json={"device_id": "DEVICE123"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["device_id"] == "DEVICE123"

        # Verify device was saved
        await async_db_session.refresh(settings)
        assert settings.fitbit_device_id == "DEVICE123"

    async def test_select_fitbit_device_missing_device_id(
        self, api_client: AsyncClient, test_user: User, async_db_session
    ):
        """Test selecting device without device_id parameter."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        response = await api_client.post(
            "/api/fitbit/device/select",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
class TestDisconnectFitbitEndpoint:
    """Test /api/fitbit/disconnect endpoint."""

    async def test_disconnect_fitbit_endpoint(
        self, api_client: AsyncClient, test_user: User, async_db_session
    ):
        """Test disconnecting Fitbit integration."""
        # Create authorized settings
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

        response = await api_client.post("/api/fitbit/disconnect")

        assert response.status_code == status.HTTP_200_OK

        # Verify settings were cleared
        await async_db_session.refresh(settings)
        assert settings.is_authorized is False
        assert settings.access_token is None
        assert settings.refresh_token is None
        assert settings.fitbit_user_id is None
        assert settings.fitbit_device_id is None

    async def test_disconnect_fitbit_when_not_connected(
        self, api_client: AsyncClient, test_user: User
    ):
        """Test disconnect when user doesn't have Fitbit connected."""
        response = await api_client.post("/api/fitbit/disconnect")

        # Should succeed (idempotent operation)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
class TestFitbitStatusEndpoint:
    """Test /api/fitbit/status endpoint."""

    async def test_get_fitbit_status_endpoint_authorized(
        self, api_client: AsyncClient, test_user: User, async_db_session
    ):
        """Test status endpoint for authorized user."""
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            fitbit_user_id="FITBIT123",
            fitbit_device_id="DEVICE456",
            is_authorized=True,
        )
        async_db_session.add(settings)
        await async_db_session.commit()

        response = await api_client.get("/api/fitbit/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_authorized"] is True
        assert data["fitbit_user_id"] == "FITBIT123"
        assert data["device_id"] == "DEVICE456"

    async def test_get_fitbit_status_endpoint_not_authorized(
        self, api_client: AsyncClient, test_user: User
    ):
        """Test status endpoint for user without Fitbit."""
        response = await api_client.get("/api/fitbit/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_authorized"] is False
        assert "fitbit_user_id" not in data

    async def test_fitbit_status_requires_authentication(self, api_client: AsyncClient):
        """Test status endpoint requires authentication."""
        from app.main import app

        async with AsyncClient(app=app, base_url="http://test") as unauth_client:
            response = await unauth_client.get("/api/fitbit/status")

            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_307_TEMPORARY_REDIRECT,
            ]


@pytest.mark.asyncio
class TestFitbitHistoricalDataEndpoint:
    """Test /api/fitbit/capture-historical endpoint."""

    async def test_capture_historical_fitbit_data(
        self, api_client: AsyncClient, test_user: User, async_db_session, sample_audio_file
    ):
        """Test capturing historical Fitbit data for existing log."""
        from app.models.log_entry import LogEntry

        # Create authorized Fitbit settings
        settings = UserFitbitSettings(
            id=uuid.uuid4(),
            user_id=test_user.id,
            access_token="valid_token",
            is_authorized=True,
        )
        async_db_session.add(settings)

        # Create a log without Fitbit data
        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        with patch("app.api.fitbit.FitbitService") as mock_service:
            mock_service.return_value.get_comprehensive_health_snapshot = AsyncMock(
                return_value={
                    "heart_rate_bpm": 70,
                    "steps_today": 5000,
                }
            )

            response = await api_client.post(
                f"/api/fitbit/capture-historical/{log.id}"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "fitbit_data_id" in data

    async def test_capture_historical_data_already_exists(
        self, api_client: AsyncClient, test_user: User, async_db_session, sample_audio_file
    ):
        """Test capturing historical data when Fitbit data already exists."""
        from app.models.log_entry import LogEntry
        from app.models.fitbit import FitbitData

        # Create log with existing Fitbit data
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
        )
        async_db_session.add(fitbit_data)
        await async_db_session.commit()

        response = await api_client.post(
            f"/api/fitbit/capture-historical/{log.id}"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already has" in response.json()["detail"].lower()

    async def test_capture_historical_data_not_authorized(
        self, api_client: AsyncClient, test_user: User, async_db_session, sample_audio_file
    ):
        """Test historical capture when user hasn't authorized Fitbit."""
        from app.models.log_entry import LogEntry

        log = LogEntry(
            id=uuid.uuid4(),
            user_id=test_user.id,
            original_filename="test.wav",
            audio_local_path=str(sample_audio_file),
        )
        async_db_session.add(log)
        await async_db_session.commit()

        response = await api_client.post(
            f"/api/fitbit/capture-historical/{log.id}"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not authorized" in response.json()["detail"].lower()
