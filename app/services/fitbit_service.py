"""Fitbit API integration service."""

import logging
from datetime import datetime, timedelta, UTC
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import requests
from requests.exceptions import HTTPError

from app.config import Settings
from app.models.fitbit import UserFitbitSettings


logger = logging.getLogger(__name__)


class FitbitAPIError(Exception):
    """Base exception for Fitbit API errors."""

    pass


class FitbitTokenExpiredError(FitbitAPIError):
    """Exception raised when Fitbit access token is expired."""

    pass


class FitbitService:
    """Service for interacting with the Fitbit API."""

    def __init__(self, settings: Settings):
        """
        Initialize the Fitbit service.

        Args:
            settings: Application settings containing Fitbit OAuth credentials
        """
        self.settings = settings
        self.client_id = settings.fitbit_oauth_client_id
        self.client_secret = settings.fitbit_oauth_client_secret
        self.base_url = "https://api.fitbit.com"
        self.auth_url = "https://www.fitbit.com/oauth2/authorize"
        self.token_url = "https://api.fitbit.com/oauth2/token"

    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Generate Fitbit OAuth authorization URL.

        Args:
            redirect_uri: Callback URL for OAuth redirect
            state: Optional state parameter for CSRF protection

        Returns:
            Full authorization URL
        """
        scopes = [
            "activity",
            "heartrate",
            "sleep",
            "oxygen_saturation",
            "profile",
            "settings",  # Required for device access
        ]

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from Fitbit
            redirect_uri: Same redirect URI used in authorization
            user_id: User ID to associate tokens with
            db: Database session

        Returns:
            Dict containing access_token, refresh_token, fitbit_user_id, expires_at
        """
        data = {
            "client_id": self.client_id,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = requests.post(
                self.token_url,
                data=data,
                headers=headers,
                auth=(self.client_id, self.client_secret),
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 28800)  # Default 8 hours
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            # Save or update user Fitbit settings
            result = await db.execute(select(UserFitbitSettings).where(UserFitbitSettings.user_id == user_id))
            settings = result.scalar_one_or_none()

            if not settings:
                settings = UserFitbitSettings(
                    id=uuid.uuid4(),
                    user_id=user_id,
                )
                db.add(settings)

            settings.access_token = token_data["access_token"]
            settings.refresh_token = token_data["refresh_token"]
            settings.fitbit_user_id = token_data.get("user_id")
            settings.token_expires_at = expires_at
            settings.is_authorized = True

            await db.commit()

            return {
                "access_token": token_data["access_token"],
                "refresh_token": token_data["refresh_token"],
                "fitbit_user_id": token_data.get("user_id"),
                "expires_at": expires_at,
            }

        except HTTPError as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            raise FitbitAPIError(f"Token exchange failed: {e}")

    async def refresh_access_token(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """
        Refresh an expired access token.

        Args:
            user_id: User ID
            db: Database session
        """
        result = await db.execute(select(UserFitbitSettings).where(UserFitbitSettings.user_id == user_id))
        settings = result.scalar_one_or_none()

        if not settings or not settings.refresh_token:
            raise FitbitAPIError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": settings.refresh_token,
        }

        try:
            response = requests.post(
                self.token_url,
                data=data,
                auth=(self.client_id, self.client_secret),
            )
            response.raise_for_status()
            token_data = response.json()

            # Update tokens
            expires_in = token_data.get("expires_in", 28800)
            settings.access_token = token_data["access_token"]
            settings.refresh_token = token_data["refresh_token"]
            settings.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            await db.commit()
            logger.info(f"Refreshed Fitbit token for user {user_id}")

        except HTTPError as e:
            logger.error(f"Failed to refresh token: {e}")
            raise FitbitAPIError(f"Token refresh failed: {e}")

    async def get_user_settings(self, user_id: uuid.UUID, db: AsyncSession) -> Optional[UserFitbitSettings]:
        """Get user's Fitbit settings from database."""
        result = await db.execute(select(UserFitbitSettings).where(UserFitbitSettings.user_id == user_id))
        return result.scalar_one_or_none()

    def _make_api_request(self, access_token: str, endpoint: str, method: str = "GET") -> Dict[str, Any]:
        """
        Make an authenticated request to the Fitbit API.

        Args:
            access_token: Fitbit access token
            endpoint: API endpoint (e.g., '/1/user/-/devices.json')
            method: HTTP method

        Returns:
            API response as dict

        Raises:
            FitbitTokenExpiredError: If token is expired (401)
            FitbitAPIError: For other API errors
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        try:
            response = requests.request(method, url, headers=headers)
            response.raise_for_status()
            return response.json()

        except HTTPError as e:
            if e.response.status_code == 401:
                raise FitbitTokenExpiredError("Access token expired")
            elif e.response.status_code == 429:
                raise FitbitAPIError("Rate limit exceeded")
            else:
                raise FitbitAPIError(f"API request failed: {e}")

    async def get_user_devices(self, access_token: str) -> List[Dict[str, Any]]:
        """
        Get list of user's Fitbit devices.

        Args:
            access_token: Fitbit access token

        Returns:
            List of device dicts with id, deviceVersion, type, batteryLevel, etc.
        """
        try:
            response = self._make_api_request(access_token, "/1/user/-/devices.json")
            # Fitbit returns an array directly at the root
            if isinstance(response, list):
                return response
            # But handle case where it might be wrapped
            elif isinstance(response, dict) and "devices" in response:
                return response["devices"]
            else:
                logger.warning(f"Unexpected devices response format: {type(response)}")
                return []
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
            raise

    async def get_user_devices_with_refresh(self, user_id: uuid.UUID, db: AsyncSession) -> List[Dict[str, Any]]:
        """Get devices with automatic token refresh if needed."""
        settings = await self.get_user_settings(user_id, db)
        if not settings or not settings.is_authorized:
            raise FitbitAPIError("User not authorized")

        if settings.is_token_expired():
            await self.refresh_access_token(user_id, db)
            await db.refresh(settings)

        return await self.get_user_devices(settings.access_token)

    async def get_current_heart_rate(self, access_token: str) -> Dict[str, Optional[int]]:
        """
        Get current heart rate data.

        Returns:
            Dict with heart_rate_bpm and resting_heart_rate_bpm
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self._make_api_request(
                access_token,
                f"/1/user/-/activities/heart/date/{today}/1d/1sec.json",
            )

            heart_rate_bpm = None
            resting_heart_rate_bpm = None

            # Get resting heart rate from previous day if today's is not available
            if "activities-heart" in data and data["activities-heart"]:
                daily_data = data["activities-heart"][0]
                if "value" in daily_data and "restingHeartRate" in daily_data["value"]:
                    resting_heart_rate_bpm = daily_data["value"]["restingHeartRate"]
            
            # If no resting heart rate for today, try yesterday
            if resting_heart_rate_bpm is None:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                yesterday_data = self._make_api_request(
                    access_token,
                    f"/1/user/-/activities/heart/date/{yesterday}/1d.json",
                )
                if "activities-heart" in yesterday_data and yesterday_data["activities-heart"]:
                    daily_data = yesterday_data["activities-heart"][0]
                    if "value" in daily_data and "restingHeartRate" in daily_data["value"]:
                        resting_heart_rate_bpm = daily_data["value"]["restingHeartRate"]

            # Get current/latest heart rate from intraday data
            if "activities-heart-intraday" in data and "dataset" in data["activities-heart-intraday"]:
                intraday = data["activities-heart-intraday"]["dataset"]
                if intraday:
                    # Get the most recent reading
                    heart_rate_bpm = intraday[-1].get("value")

            return {
                "heart_rate_bpm": heart_rate_bpm,
                "resting_heart_rate_bpm": resting_heart_rate_bpm,
            }

        except Exception as e:
            logger.error(f"Failed to get heart rate: {e}")
            return {"heart_rate_bpm": None, "resting_heart_rate_bpm": None}

    async def get_sleep_data(self, access_token: str) -> Dict[str, Optional[float]]:
        """
        Get latest sleep summary.

        Returns:
            Dict with sleep_score, sleep_duration_minutes, sleep_efficiency_pct
        """
        try:
            # Get yesterday's date since sleep data is typically from the previous night
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            data = self._make_api_request(
                access_token,
                f"/1.2/user/-/sleep/date/{yesterday}.json",
            )

            if not data.get("sleep"):
                return {
                    "sleep_score": None,
                    "sleep_duration_minutes": None,
                    "sleep_efficiency_pct": None,
                }

            sleep_record = data["sleep"][0]
            efficiency = sleep_record.get("efficiency")

            # Calculate sleep score based on efficiency and deep sleep percentage
            sleep_score = None
            if efficiency:
                sleep_score = int(efficiency * 0.8)  # Simplified score calculation

            return {
                "sleep_score": sleep_score,
                "sleep_duration_minutes": data.get("summary", {}).get("totalMinutesAsleep"),
                "sleep_efficiency_pct": float(efficiency) if efficiency else None,
            }

        except Exception as e:
            logger.error(f"Failed to get sleep data: {e}")
            return {
                "sleep_score": None,
                "sleep_duration_minutes": None,
                "sleep_efficiency_pct": None,
            }

    async def get_activity_summary(self, access_token: str) -> Dict[str, Optional[float]]:
        """
        Get today's activity summary.

        Returns:
            Dict with steps_today, calories_burned_today, active_minutes_today, etc.
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self._make_api_request(
                access_token,
                f"/1/user/-/activities/date/{today}.json",
            )

            summary = data.get("summary", {})

            # Calculate total active minutes
            very_active = summary.get("veryActiveMinutes", 0)
            fairly_active = summary.get("fairlyActiveMinutes", 0)
            active_minutes = very_active + fairly_active

            # Get total distance
            distance = 0.0
            for dist in summary.get("distances", []):
                if dist.get("activity") == "total":
                    distance = dist.get("distance", 0.0)

            return {
                "steps_today": summary.get("steps"),
                "calories_burned_today": summary.get("caloriesOut"),
                "active_minutes_today": active_minutes,
                "distance_today_miles": distance,
                "floors_climbed_today": summary.get("floors"),
            }

        except Exception as e:
            logger.error(f"Failed to get activity summary: {e}")
            return {
                "steps_today": None,
                "calories_burned_today": None,
                "active_minutes_today": None,
                "distance_today_miles": None,
                "floors_climbed_today": None,
            }

    async def get_spo2_data(self, access_token: str) -> Dict[str, Optional[float]]:
        """
        Get blood oxygen (SpO2) data.

        Returns:
            Dict with blood_oxygen_pct
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self._make_api_request(
                access_token,
                f"/1/user/-/spo2/date/{today}.json",
            )

            if not data or "value" not in data:
                return {"blood_oxygen_pct": None}

            avg_spo2 = data["value"].get("avg")
            return {"blood_oxygen_pct": avg_spo2}

        except Exception as e:
            logger.error(f"Failed to get SpO2 data: {e}")
            return {"blood_oxygen_pct": None}

    async def get_comprehensive_health_snapshot(self, access_token: str) -> Dict[str, Any]:
        """
        Get all available health metrics in one call.

        Returns:
            Combined dict with all health metrics
        """
        result = {}

        try:
            # Get heart rate data
            heart_data = await self.get_current_heart_rate(access_token)
            result.update(heart_data)
        except Exception as e:
            logger.warning(f"Failed to get heart rate in snapshot: {e}")

        try:
            # Get sleep data
            sleep_data = await self.get_sleep_data(access_token)
            result.update(sleep_data)
        except Exception as e:
            logger.warning(f"Failed to get sleep data in snapshot: {e}")

        try:
            # Get activity data
            activity_data = await self.get_activity_summary(access_token)
            result.update(activity_data)
        except Exception as e:
            logger.warning(f"Failed to get activity data in snapshot: {e}")

        try:
            # Get SpO2 data
            spo2_data = await self.get_spo2_data(access_token)
            result.update(spo2_data)
        except Exception as e:
            logger.warning(f"Failed to get SpO2 data in snapshot: {e}")

        return result
