import enum
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Enum, Float, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    VECTORIZING = "vectorizing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class MediaType(enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


class LogType(enum.Enum):
    PERSONAL = "personal"
    SHIP = "ship"


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # User relationship
    user_id = Column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    user = relationship("User", back_populates="authored_logs")
    
    # Media information
    media_type = Column(Enum(MediaType), nullable=False, default=MediaType.AUDIO)
    original_filename = Column(String, nullable=True)
    is_video_source = Column(Boolean, nullable=False, default=False)

    # Log classification
    log_type = Column(Enum(LogType), nullable=False, default=LogType.SHIP)
    
    # Video storage (if video source)
    video_s3_key = Column(String, nullable=True)
    video_local_path = Column(String, nullable=True)
    
    # Audio storage (extracted from video if applicable)
    audio_s3_key = Column(String, nullable=True)
    audio_local_path = Column(String, nullable=True)
    
    # Processing results
    transcription = Column(Text, nullable=True)
    embedding = Column(Vector(1536), nullable=True)  # dimension for text-embedding-3-small
    summary = Column(Text, nullable=True)
    processing_status = Column(
        Enum(ProcessingStatus),
        nullable=False,
        default=ProcessingStatus.PENDING
    )
    processing_error = Column(Text, nullable=True)
    
    # Location information
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String, nullable=True)
    location_city = Column(String, nullable=True)
    location_state = Column(String, nullable=True)
    location_country = Column(String, nullable=True)
    body_of_water = Column(String, nullable=True)
    nearest_port = Column(String, nullable=True)
    
    # Weather/Marine conditions at time of log
    weather_air_temp_f = Column(Float, nullable=True)
    weather_water_temp_f = Column(Float, nullable=True)
    weather_wind_speed_kts = Column(Float, nullable=True)
    weather_wind_direction_deg = Column(Float, nullable=True)
    weather_wind_gust_kts = Column(Float, nullable=True)
    weather_wave_height_ft = Column(Float, nullable=True)
    weather_wave_period_sec = Column(Float, nullable=True)
    weather_barometric_pressure_mb = Column(Float, nullable=True)
    weather_visibility_nm = Column(Float, nullable=True)
    weather_conditions = Column(String, nullable=True)  # "Clear", "Overcast", etc.
    weather_forecast = Column(Text, nullable=True)  # Short text forecast
    weather_captured_at = Column(DateTime, nullable=True)  # When weather data was captured
    weather_relative_humidity_pct = Column(Float, nullable=True)  # Relative humidity percentage
    weather_dew_point_f = Column(Float, nullable=True)  # Dew point temperature in Fahrenheit
    weather_precipitation_probability_pct = Column(Float, nullable=True)  # Probability of precipitation percentage
    weather_precipitation_amount_in = Column(Float, nullable=True)  # Quantitative precipitation in inches
    
    def __repr__(self):
        return f"<LogEntry(id={self.id}, created_at={self.created_at}, status={self.processing_status.value})>"