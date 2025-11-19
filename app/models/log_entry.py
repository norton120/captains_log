import enum
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    VECTORIZING = "vectorizing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class LogEntry(Base):
    __tablename__ = "log_entries"
    
    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    audio_s3_key = Column(String, nullable=False)
    transcription = Column(Text, nullable=True)
    embedding = Column(Vector(1536), nullable=True)  # dimension for text-embedding-3-small
    summary = Column(Text, nullable=True)
    processing_status = Column(
        Enum(ProcessingStatus), 
        nullable=False, 
        default=ProcessingStatus.PENDING
    )
    processing_error = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<LogEntry(id={self.id}, created_at={self.created_at}, status={self.processing_status.value})>"