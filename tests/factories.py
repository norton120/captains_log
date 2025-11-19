"""Test data factories using factory-boy."""
import factory
from factory import Faker, LazyAttribute, SubFactory
from datetime import datetime
from uuid import uuid4

from app.models.log_entry import LogEntry, ProcessingStatus


class LogEntryFactory(factory.Factory):
    """Factory for creating LogEntry instances."""
    
    class Meta:
        model = LogEntry
    
    id = factory.LazyFunction(uuid4)
    created_at = factory.LazyFunction(datetime.utcnow)
    audio_s3_key = factory.Sequence(lambda n: f"audio/test-entry-{n}.wav")
    transcription = Faker("text", max_nb_chars=500)
    embedding = factory.LazyAttribute(lambda obj: [0.1] * 1536)  # Mock embedding
    summary = Faker("text", max_nb_chars=200)
    processing_status = ProcessingStatus.COMPLETED
    processing_error = None


class PendingLogEntryFactory(LogEntryFactory):
    """Factory for pending log entries."""
    
    transcription = None
    embedding = None
    summary = None
    processing_status = ProcessingStatus.PENDING


class FailedLogEntryFactory(LogEntryFactory):
    """Factory for failed log entries."""
    
    transcription = None
    embedding = None
    summary = None
    processing_status = ProcessingStatus.FAILED
    processing_error = Faker("sentence")


class ProcessingLogEntryFactory(LogEntryFactory):
    """Factory for log entries in various processing states."""
    
    transcription = None
    embedding = None
    summary = None
    processing_status = factory.Iterator([
        ProcessingStatus.TRANSCRIBING,
        ProcessingStatus.VECTORIZING,
        ProcessingStatus.SUMMARIZING
    ])