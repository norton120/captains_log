"""Tests for Fitbit service."""
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, AsyncMock, patch
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.fitbit_service import FitbitService, FitbitAPIError, FitbitTokenExpiredError
from app.models.fitbit import UserFitbitSettings
from app.models.user import User
from app.config import Settings


@pytest.fixture
def mock_fitbit_client():
    """Mock Fitbit SDK client."""
    client = Mock()
    client.client_id = "test_client_id"
    client.client_secret = "test_client_secret"
    return client


@pytest.fixture
def fitbit_service(test_settings: Settings, mock_fitbit_client):
    """Create FitbitService instance with mocked client."""
    with patch("app.services.fitbit_service.Fitbit", return_value=mock_fitbit_client):
        service = FitbitService(test_settings)
        service.client = mock_fitbit_client
        return service


@pytest.fixture
def user_fitbit_settings(test_user: User):
    """Create UserFitbitSettings for test user."""
    return UserFitbitSettings(
        id=uuid.uuid4(),
        user_id=test_user.id,
        fitbit_user_id="FITBIT123",
        fitbit_device_id="DEVICE456",
        access_token="valid_access_token",
        refresh_token="valid_refresh_token",
        token_expires_at=datetime.now(UTC) + timedelta(hours=8),
        is_authorized=True,
    )


@pytest.mark.asyncio
class TestFitbitServiceInitialization:
    """Test FitbitService initialization."""

    async def test_fitbit_service_initialization(self, test_settings: Settings):
        """Verify FitbitService initializes with settings."""
        service = FitbitService(test_settings)
        assert service.settings == test_settings
        assert service.client_id == test_settings.fitbit_oauth_client_id
        assert service.client_secret == test_settings.fitbit_oauth_client_secret


@pytest.mark.asyncio
class TestFitbitOAuthFlow:
    """Test Fitbit OAuth authorization flow."""

    async def test_get_authorization_url(self, fitbit_service: FitbitService):
        """Test OAuth authorization URL generation."""
        fitbit_service.client.authorize_token_url = Mock(
            return_value="https://www.fitbit.com/oauth2/authorize?client_id=test&scope=activity+heartrate+sleep+oxygen_saturation+profile&redirect_uri=http://localhost/callback"
        )

        url = fitbit_service.get_authorization_url(
            redirect_uri="http://localhost/callback"
        )

        assert "https://www.fitbit.com/oauth2/authorize" in url
        assert "client_id=test" in url
        assert "activity" in url
        assert "heartrate" in url
        assert "sleep" in url
        assert "oxygen_saturation" in url

    async def test_exchange_code_for_tokens(
        self, fitbit_service: FitbitService, async_db_session: AsyncSession, test_user: User
    ):
        """Test OAuth code exchange for access/refresh tokens."""
        # Mock the token exchange response
        fitbit_service.client.fetch_token = Mock(
            return_value={
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "expires_at": (datetime.now(UTC) + timedelta(hours=8)).timestamp(),
                "user_id": "FITBIT123",
            }
        )

        result = await fitbit_service.exchange_code_for_tokens(
            code="auth_code_123",
            redirect_uri="http://localhost/callback",
            user_id=test_user.id,
            db=async_db_session,
        )

        assert result["access_token"] == "new_access_token"
        assert result["refresh_token"] == "new_refresh_token"
        assert result["fitbit_user_id"] == "FITBIT123"

        # Verify settings were saved to database
        settings = await fitbit_service.get_user_settings(test_user.id, async_db_session)
        assert settings.access_token == "new_access_token"
        assert settings.is_authorized is True

    async def test_refresh_access_token(
        self,
        fitbit_service: FitbitService,
        async_db_session: AsyncSession,
        test_user: User,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test token refresh when expired."""
        # Save expired settings
        user_fitbit_settings.token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        async_db_session.add(user_fitbit_settings)
        await async_db_session.commit()

        # Mock token refresh
        new_expires_at = datetime.now(UTC) + timedelta(hours=8)
        fitbit_service.client.refresh_token = Mock(
            return_value={
                "access_token": "refreshed_access_token",
                "refresh_token": "refreshed_refresh_token",
                "expires_at": new_expires_at.timestamp(),
            }
        )

        await fitbit_service.refresh_access_token(test_user.id, async_db_session)

        # Verify tokens were updated
        settings = await fitbit_service.get_user_settings(test_user.id, async_db_session)
        assert settings.access_token == "refreshed_access_token"
        assert settings.refresh_token == "refreshed_refresh_token"
        assert settings.token_expires_at > datetime.now(UTC)


@pytest.mark.asyncio
class TestFitbitDevices:
    """Test Fitbit device management."""

    async def test_get_user_devices(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching user's Fitbit devices."""
        # Mock devices API response
        fitbit_service.client.get_devices = Mock(
            return_value=[
                {
                    "id": "DEVICE123",
                    "deviceVersion": "Charge 5",
                    "type": "TRACKER",
                    "batteryLevel": 75,
                    "lastSyncTime": "2025-11-22T10:30:00.000",
                },
                {
                    "id": "DEVICE456",
                    "deviceVersion": "Versa 3",
                    "type": "WATCH",
                    "batteryLevel": 50,
                    "lastSyncTime": "2025-11-21T08:00:00.000",
                },
            ]
        )

        devices = await fitbit_service.get_user_devices(user_fitbit_settings.access_token)

        assert len(devices) == 2
        assert devices[0]["id"] == "DEVICE123"
        assert devices[0]["deviceVersion"] == "Charge 5"
        assert devices[1]["id"] == "DEVICE456"


@pytest.mark.asyncio
class TestFitbitHealthData:
    """Test Fitbit health data retrieval."""

    async def test_get_current_heart_rate(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching current heart rate."""
        # Mock heart rate API response
        fitbit_service.client.intraday_time_series = Mock(
            return_value={
                "activities-heart": [
                    {
                        "dateTime": "2025-11-22",
                        "value": {
                            "restingHeartRate": 58,
                        },
                    }
                ],
                "activities-heart-intraday": {
                    "dataset": [
                        {"time": "10:30:00", "value": 72},
                    ]
                },
            }
        )

        result = await fitbit_service.get_current_heart_rate(
            user_fitbit_settings.access_token
        )

        assert result["heart_rate_bpm"] == 72
        assert result["resting_heart_rate_bpm"] == 58

    async def test_get_current_heart_rate_no_data(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching heart rate when no recent data available."""
        fitbit_service.client.intraday_time_series = Mock(
            return_value={
                "activities-heart-intraday": {"dataset": []}
            }
        )

        result = await fitbit_service.get_current_heart_rate(
            user_fitbit_settings.access_token
        )

        assert result["heart_rate_bpm"] is None

    async def test_get_sleep_data(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching latest sleep summary."""
        fitbit_service.client.get_sleep = Mock(
            return_value={
                "sleep": [
                    {
                        "efficiency": 92,
                        "duration": 27000000,  # milliseconds (7.5 hours)
                        "levels": {
                            "summary": {
                                "deep": {"minutes": 90},
                                "light": {"minutes": 240},
                                "rem": {"minutes": 120},
                            }
                        },
                    }
                ],
                "summary": {
                    "totalMinutesAsleep": 450,
                    "totalTimeInBed": 490,
                },
            }
        )

        result = await fitbit_service.get_sleep_data(user_fitbit_settings.access_token)

        assert result["sleep_duration_minutes"] == 450
        assert result["sleep_efficiency_pct"] == 92.0
        # Sleep score calculation: (efficiency * 0.5 + deep_pct * 0.5)
        assert result["sleep_score"] is not None

    async def test_get_activity_summary(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching today's activity summary."""
        fitbit_service.client.activities = Mock(
            return_value={
                "summary": {
                    "steps": 8432,
                    "caloriesOut": 2145,
                    "veryActiveMinutes": 30,
                    "fairlyActiveMinutes": 15,
                    "distances": [{"activity": "total", "distance": 4.2}],
                    "floors": 12,
                }
            }
        )

        result = await fitbit_service.get_activity_summary(
            user_fitbit_settings.access_token
        )

        assert result["steps_today"] == 8432
        assert result["calories_burned_today"] == 2145
        assert result["active_minutes_today"] == 45  # very + fairly
        assert result["distance_today_miles"] == 4.2
        assert result["floors_climbed_today"] == 12

    async def test_get_spo2_data(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching blood oxygen (SpO2) data."""
        fitbit_service.client.get_spo2 = Mock(
            return_value={
                "dateTime": "2025-11-22",
                "value": {"avg": 98.5, "min": 95.0, "max": 100.0},
            }
        )

        result = await fitbit_service.get_spo2_data(user_fitbit_settings.access_token)

        assert result["blood_oxygen_pct"] == 98.5

    async def test_get_spo2_data_no_sensor(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching SpO2 when device doesn't have sensor."""
        fitbit_service.client.get_spo2 = Mock(return_value=None)

        result = await fitbit_service.get_spo2_data(user_fitbit_settings.access_token)

        assert result["blood_oxygen_pct"] is None

    async def test_get_comprehensive_health_snapshot(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test fetching all health data at once."""
        # Mock all API endpoints
        fitbit_service.get_current_heart_rate = AsyncMock(
            return_value={"heart_rate_bpm": 72, "resting_heart_rate_bpm": 58}
        )
        fitbit_service.get_sleep_data = AsyncMock(
            return_value={"sleep_score": 85, "sleep_duration_minutes": 450}
        )
        fitbit_service.get_activity_summary = AsyncMock(
            return_value={"steps_today": 8432, "calories_burned_today": 2145}
        )
        fitbit_service.get_spo2_data = AsyncMock(
            return_value={"blood_oxygen_pct": 98.5}
        )

        result = await fitbit_service.get_comprehensive_health_snapshot(
            user_fitbit_settings.access_token
        )

        assert result["heart_rate_bpm"] == 72
        assert result["sleep_score"] == 85
        assert result["steps_today"] == 8432
        assert result["blood_oxygen_pct"] == 98.5

    async def test_get_comprehensive_health_snapshot_handles_partial_failures(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test comprehensive snapshot handles partial API failures gracefully."""
        # Mock some endpoints to succeed, some to fail
        fitbit_service.get_current_heart_rate = AsyncMock(
            return_value={"heart_rate_bpm": 72}
        )
        fitbit_service.get_sleep_data = AsyncMock(side_effect=FitbitAPIError("Sleep API failed"))
        fitbit_service.get_activity_summary = AsyncMock(
            return_value={"steps_today": 8432}
        )
        fitbit_service.get_spo2_data = AsyncMock(side_effect=FitbitAPIError("SpO2 unavailable"))

        result = await fitbit_service.get_comprehensive_health_snapshot(
            user_fitbit_settings.access_token
        )

        # Should have data that succeeded
        assert result["heart_rate_bpm"] == 72
        assert result["steps_today"] == 8432
        # Failed calls should return None or be omitted
        assert "sleep_score" not in result or result["sleep_score"] is None


@pytest.mark.asyncio
class TestFitbitErrorHandling:
    """Test Fitbit API error handling."""

    async def test_fitbit_api_401_unauthorized(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test handling of 401 unauthorized error."""
        from requests.exceptions import HTTPError

        response = Mock()
        response.status_code = 401
        fitbit_service.client.get_devices = Mock(
            side_effect=HTTPError(response=response)
        )

        with pytest.raises(FitbitTokenExpiredError):
            await fitbit_service.get_user_devices(user_fitbit_settings.access_token)

    async def test_fitbit_api_429_rate_limit(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test handling of 429 rate limit error."""
        from requests.exceptions import HTTPError

        response = Mock()
        response.status_code = 429
        fitbit_service.client.get_devices = Mock(
            side_effect=HTTPError(response=response)
        )

        with pytest.raises(FitbitAPIError) as exc_info:
            await fitbit_service.get_user_devices(user_fitbit_settings.access_token)

        assert "rate limit" in str(exc_info.value).lower()

    async def test_fitbit_api_500_server_error(
        self,
        fitbit_service: FitbitService,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test handling of 500 server error."""
        from requests.exceptions import HTTPError

        response = Mock()
        response.status_code = 500
        fitbit_service.client.get_devices = Mock(
            side_effect=HTTPError(response=response)
        )

        with pytest.raises(FitbitAPIError):
            await fitbit_service.get_user_devices(user_fitbit_settings.access_token)

    async def test_fitbit_token_auto_refresh(
        self,
        fitbit_service: FitbitService,
        async_db_session: AsyncSession,
        test_user: User,
        user_fitbit_settings: UserFitbitSettings,
    ):
        """Test automatic token refresh when token is expired."""
        # Set token as expired
        user_fitbit_settings.token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        async_db_session.add(user_fitbit_settings)
        await async_db_session.commit()

        # Mock refresh and successful retry
        fitbit_service.refresh_access_token = AsyncMock()
        fitbit_service.client.get_devices = Mock(return_value=[])

        # This should trigger auto-refresh
        await fitbit_service.get_user_devices_with_refresh(
            test_user.id, async_db_session
        )

        # Verify refresh was called
        fitbit_service.refresh_access_token.assert_called_once()
