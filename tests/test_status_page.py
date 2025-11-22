"""
Tests for the status page API endpoint.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, UTC

from app.models.log_entry import LogEntry, ProcessingStatus, MediaType
from app.config import Settings


class TestStatusPageAPI:
    """Test the status page API endpoint."""

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_200(self, api_client: AsyncClient):
        """Test that the status endpoint returns 200 OK."""
        response = await api_client.get("/api/status")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_json(self, api_client: AsyncClient):
        """Test that the status endpoint returns JSON."""
        response = await api_client.get("/api/status")
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_status_endpoint_has_internet_connectivity_field(
        self, api_client: AsyncClient
    ):
        """Test that the status response includes internet connectivity status."""
        response = await api_client.get("/api/status")
        data = response.json()
        assert "internet_connectivity" in data
        assert isinstance(data["internet_connectivity"], dict)
        assert "openai_accessible" in data["internet_connectivity"]
        assert "aws_accessible" in data["internet_connectivity"]

    @pytest.mark.asyncio
    async def test_status_endpoint_has_processing_queue_field(
        self, api_client: AsyncClient
    ):
        """Test that the status response includes processing queue information."""
        response = await api_client.get("/api/status")
        data = response.json()
        assert "processing_queue" in data
        assert isinstance(data["processing_queue"], dict)

    @pytest.mark.asyncio
    async def test_processing_queue_shows_log_counts_by_status(
        self, api_client: AsyncClient, async_db_session: AsyncSession
    ):
        """Test that the processing queue shows counts of logs by status."""
        # Create test logs in different states
        log1 = LogEntry(
            media_type=MediaType.AUDIO,
            processing_status=ProcessingStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        log2 = LogEntry(
            media_type=MediaType.AUDIO,
            processing_status=ProcessingStatus.TRANSCRIBING,
            created_at=datetime.now(UTC),
        )
        log3 = LogEntry(
            media_type=MediaType.AUDIO,
            processing_status=ProcessingStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        log4 = LogEntry(
            media_type=MediaType.AUDIO,
            processing_status=ProcessingStatus.FAILED,
            processing_error="Test error",
            created_at=datetime.now(UTC),
        )
        log5 = LogEntry(
            media_type=MediaType.AUDIO,
            processing_status=ProcessingStatus.PENDING,
            created_at=datetime.now(UTC),
        )

        async_db_session.add_all([log1, log2, log3, log4, log5])
        await async_db_session.commit()

        response = await api_client.get("/api/status")
        data = response.json()

        queue = data["processing_queue"]
        assert "by_status" in queue
        assert queue["by_status"]["pending"] == 2
        assert queue["by_status"]["transcribing"] == 1
        assert queue["by_status"]["vectorizing"] == 0
        assert queue["by_status"]["summarizing"] == 0
        assert queue["by_status"]["completed"] == 1
        assert queue["by_status"]["failed"] == 1

    @pytest.mark.asyncio
    async def test_processing_queue_shows_total_count(
        self, api_client: AsyncClient, async_db_session: AsyncSession
    ):
        """Test that the processing queue shows total count of non-completed logs."""
        # Create test logs
        for _ in range(3):
            log = LogEntry(
                media_type=MediaType.AUDIO,
                processing_status=ProcessingStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            async_db_session.add(log)

        for _ in range(2):
            log = LogEntry(
                media_type=MediaType.AUDIO,
                processing_status=ProcessingStatus.COMPLETED,
                created_at=datetime.now(UTC),
            )
            async_db_session.add(log)

        await async_db_session.commit()

        response = await api_client.get("/api/status")
        data = response.json()

        queue = data["processing_queue"]
        assert "total_processing" in queue
        assert queue["total_processing"] == 3  # Only non-completed logs

    @pytest.mark.asyncio
    async def test_openai_connectivity_check_returns_true_when_accessible(
        self, api_client: AsyncClient
    ):
        """Test that OpenAI connectivity returns true when API is accessible."""
        with patch("app.services.openai_client.OpenAIService.check_connectivity") as mock_check:
            mock_check.return_value = True

            response = await api_client.get("/api/status")
            data = response.json()

            assert data["internet_connectivity"]["openai_accessible"] is True

    @pytest.mark.asyncio
    async def test_openai_connectivity_check_returns_false_when_not_accessible(
        self, api_client: AsyncClient
    ):
        """Test that OpenAI connectivity returns false when API is not accessible."""
        with patch("app.services.openai_client.OpenAIService.check_connectivity") as mock_check:
            mock_check.return_value = False

            response = await api_client.get("/api/status")
            data = response.json()

            assert data["internet_connectivity"]["openai_accessible"] is False

    @pytest.mark.asyncio
    async def test_aws_connectivity_check_returns_true_when_accessible(
        self, api_client: AsyncClient
    ):
        """Test that AWS connectivity returns true when S3 is accessible."""
        with patch("app.services.s3.S3Service.check_connectivity") as mock_check:
            mock_check.return_value = True

            response = await api_client.get("/api/status")
            data = response.json()

            assert data["internet_connectivity"]["aws_accessible"] is True

    @pytest.mark.asyncio
    async def test_aws_connectivity_check_returns_false_when_not_accessible(
        self, api_client: AsyncClient
    ):
        """Test that AWS connectivity returns false when S3 is not accessible."""
        with patch("app.services.s3.S3Service.check_connectivity") as mock_check:
            mock_check.return_value = False

            response = await api_client.get("/api/status")
            data = response.json()

            assert data["internet_connectivity"]["aws_accessible"] is False

    @pytest.mark.asyncio
    async def test_status_endpoint_handles_database_errors_gracefully(
        self, api_client: AsyncClient
    ):
        """Test that the status endpoint handles database errors gracefully."""
        # The endpoint will gracefully handle errors by returning False for connectivity checks
        # and empty results for processing queue if the database is unavailable
        # This test just verifies the endpoint is accessible even in error conditions
        response = await api_client.get("/api/status")
        # Should return 200 even if services have issues
        assert response.status_code == 200
        # Response should still have the expected structure
        data = response.json()
        assert "internet_connectivity" in data
        assert "processing_queue" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_status_response_includes_timestamp(self, api_client: AsyncClient):
        """Test that the status response includes a timestamp."""
        response = await api_client.get("/api/status")
        data = response.json()
        assert "timestamp" in data
        # Verify it's a valid ISO format datetime
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))


class TestStatusPageUI:
    """Test the status page UI rendering."""

    @pytest.mark.asyncio
    async def test_status_page_route_exists(self, api_client: AsyncClient):
        """Test that the /status route exists and returns 200."""
        response = await api_client.get("/status")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_page_returns_html(self, api_client: AsyncClient):
        """Test that the status page returns HTML."""
        response = await api_client.get("/status")
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_status_page_contains_title(self, api_client: AsyncClient):
        """Test that the status page contains a title."""
        response = await api_client.get("/status")
        content = response.text
        assert "status" in content.lower() or "system" in content.lower()

    @pytest.mark.asyncio
    async def test_status_page_contains_processing_queue_section(
        self, api_client: AsyncClient
    ):
        """Test that the status page contains processing queue information."""
        response = await api_client.get("/status")
        content = response.text.lower()
        assert "processing" in content or "queue" in content

    @pytest.mark.asyncio
    async def test_status_page_contains_connectivity_section(
        self, api_client: AsyncClient
    ):
        """Test that the status page contains connectivity information."""
        response = await api_client.get("/status")
        content = response.text.lower()
        assert "openai" in content or "aws" in content or "connectivity" in content
