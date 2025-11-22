"""
API routes for system status page.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime, UTC
from typing import Dict

from app.dependencies import get_db_session
from app.models.log_entry import LogEntry, ProcessingStatus
from app.services.openai_client import OpenAIService
from app.services.s3 import S3Service
from app.config import Settings
from app.dependencies import get_settings


router = APIRouter()


class InternetConnectivityStatus(BaseModel):
    """Internet connectivity status for external services."""
    openai_accessible: bool
    aws_accessible: bool


class ProcessingQueueStatus(BaseModel):
    """Processing queue status with counts by status."""
    total_processing: int
    by_status: Dict[str, int]


class SystemStatusResponse(BaseModel):
    """Response model for system status."""
    timestamp: datetime
    internet_connectivity: InternetConnectivityStatus
    processing_queue: ProcessingQueueStatus


@router.get("", response_model=SystemStatusResponse)
async def get_system_status(
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SystemStatusResponse:
    """
    Get system status including internet connectivity and processing queue.

    Returns:
        - timestamp: Current timestamp
        - internet_connectivity: Status of OpenAI and AWS connections
        - processing_queue: Counts of logs by processing status
    """
    # Check internet connectivity
    openai_accessible = await check_openai_connectivity(settings)
    aws_accessible = await check_aws_connectivity(settings)

    # Get processing queue status
    processing_stats = await get_processing_queue_stats(db_session)

    return SystemStatusResponse(
        timestamp=datetime.now(UTC),
        internet_connectivity=InternetConnectivityStatus(
            openai_accessible=openai_accessible,
            aws_accessible=aws_accessible,
        ),
        processing_queue=ProcessingQueueStatus(
            total_processing=processing_stats["total_processing"],
            by_status=processing_stats["by_status"],
        ),
    )


async def check_openai_connectivity(settings: Settings) -> bool:
    """
    Check if OpenAI API is accessible.

    Args:
        settings: Application settings

    Returns:
        True if OpenAI API is accessible, False otherwise
    """
    try:
        openai_service = OpenAIService(settings)
        return await openai_service.check_connectivity()
    except Exception:
        return False


async def check_aws_connectivity(settings: Settings) -> bool:
    """
    Check if AWS S3 is accessible.

    Args:
        settings: Application settings

    Returns:
        True if AWS S3 is accessible, False otherwise
    """
    try:
        s3_service = S3Service(settings)
        return await s3_service.check_connectivity()
    except Exception:
        return False


async def get_processing_queue_stats(db_session: AsyncSession) -> Dict:
    """
    Get statistics about the processing queue.

    Args:
        db_session: Database session

    Returns:
        Dictionary with total_processing count and counts by status
    """
    # Get counts for all statuses in a single query using GROUP BY
    result = await db_session.execute(
        select(
            LogEntry.processing_status,
            func.count(LogEntry.id)
        ).group_by(LogEntry.processing_status)
    )

    # Build status counts dictionary, initializing all statuses to 0
    status_counts = {status.value: 0 for status in ProcessingStatus}

    # Update with actual counts from database
    for status, count in result:
        status_counts[status.value] = count

    # Calculate total processing (all non-completed/failed logs)
    total_processing = sum(
        count for status, count in status_counts.items()
        if status not in ["completed", "failed"]
    )

    return {
        "total_processing": total_processing,
        "by_status": status_counts,
    }
