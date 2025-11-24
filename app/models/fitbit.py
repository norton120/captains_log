"""Fitbit-related database models."""

from datetime import datetime, UTC
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.log_entry import Base


class UserFitbitSettings(Base):
    """User-specific Fitbit OAuth settings and device configuration."""

    __tablename__ = "user_fitbit_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)

    # Fitbit user and device identifiers
    fitbit_user_id = Column(String(255), nullable=True)
    fitbit_device_id = Column(String(255), nullable=True)

    # OAuth tokens
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Authorization status
    is_authorized = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    user = relationship("User", back_populates="fitbit_settings")

    def is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self.token_expires_at:
            return True
        return datetime.now(UTC) >= self.token_expires_at

    def clear_tokens(self):
        """Clear all Fitbit tokens and authorization data."""
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.fitbit_user_id = None
        self.fitbit_device_id = None
        self.is_authorized = False


class FitbitData(Base):
    """Health and fitness data from Fitbit linked to a log entry."""

    __tablename__ = "fitbit_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_entry_id = Column(UUID(as_uuid=True), ForeignKey("log_entries.id"), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Timestamp when data was captured
    captured_at = Column(DateTime(timezone=True), nullable=False)

    # Heart rate data
    heart_rate_bpm = Column(Integer, nullable=True)
    resting_heart_rate_bpm = Column(Integer, nullable=True)

    # Sleep data
    sleep_score = Column(Integer, nullable=True)  # 0-100
    sleep_duration_minutes = Column(Integer, nullable=True)
    sleep_efficiency_pct = Column(Float, nullable=True)

    # Blood oxygen (SpO2)
    blood_oxygen_pct = Column(Float, nullable=True)

    # Activity data (for the day)
    steps_today = Column(Integer, nullable=True)
    calories_burned_today = Column(Integer, nullable=True)
    active_minutes_today = Column(Integer, nullable=True)
    distance_today_miles = Column(Float, nullable=True)
    floors_climbed_today = Column(Integer, nullable=True)

    # Cardio fitness
    vo2_max = Column(Float, nullable=True)
    cardio_fitness_score = Column(Integer, nullable=True)

    # Stress
    stress_score = Column(Integer, nullable=True)

    # Relationships
    log_entry = relationship("LogEntry", back_populates="fitbit_data")
    user = relationship("User")
