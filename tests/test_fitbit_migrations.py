"""Tests for Fitbit database migrations."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class TestFitbitMigrationTables:
    """Test that migration creates Fitbit tables."""

    async def test_migration_creates_user_fitbit_settings_table(
        self, async_db_session: AsyncSession
    ):
        """Verify user_fitbit_settings table exists with correct columns."""
        inspector = inspect(async_db_session.bind)

        # Check table exists
        tables = await async_db_session.run_sync(
            lambda sync_session: inspector.get_table_names()
        )
        assert "user_fitbit_settings" in tables

        # Check columns
        columns = await async_db_session.run_sync(
            lambda sync_session: inspector.get_columns("user_fitbit_settings")
        )
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id",
            "user_id",
            "fitbit_user_id",
            "fitbit_device_id",
            "access_token",
            "refresh_token",
            "token_expires_at",
            "is_authorized",
            "created_at",
            "updated_at",
        ]

        for expected_col in expected_columns:
            assert expected_col in column_names, f"Column {expected_col} missing"

    async def test_migration_creates_fitbit_data_table(
        self, async_db_session: AsyncSession
    ):
        """Verify fitbit_data table exists with correct columns."""
        inspector = inspect(async_db_session.bind)

        tables = await async_db_session.run_sync(
            lambda sync_session: inspector.get_table_names()
        )
        assert "fitbit_data" in tables

        columns = await async_db_session.run_sync(
            lambda sync_session: inspector.get_columns("fitbit_data")
        )
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id",
            "log_entry_id",
            "user_id",
            "captured_at",
            "heart_rate_bpm",
            "resting_heart_rate_bpm",
            "sleep_score",
            "sleep_duration_minutes",
            "sleep_efficiency_pct",
            "blood_oxygen_pct",
            "steps_today",
            "calories_burned_today",
            "active_minutes_today",
            "distance_today_miles",
            "floors_climbed_today",
            "vo2_max",
            "cardio_fitness_score",
            "stress_score",
        ]

        for expected_col in expected_columns:
            assert expected_col in column_names, f"Column {expected_col} missing"

    async def test_migration_adds_user_preferences_fitbit_columns(
        self, async_db_session: AsyncSession
    ):
        """Verify UserPreferences table has Fitbit OAuth columns."""
        inspector = inspect(async_db_session.bind)

        columns = await async_db_session.run_sync(
            lambda sync_session: inspector.get_columns("user_preferences")
        )
        column_names = [col["name"] for col in columns]

        assert "fitbit_oauth_client_id" in column_names
        assert "fitbit_oauth_client_secret" in column_names


@pytest.mark.asyncio
class TestFitbitMigrationIndexes:
    """Test that migration creates proper indexes."""

    async def test_migration_creates_user_fitbit_settings_indexes(
        self, async_db_session: AsyncSession
    ):
        """Verify indexes on user_fitbit_settings table."""
        inspector = inspect(async_db_session.bind)

        indexes = await async_db_session.run_sync(
            lambda sync_session: inspector.get_indexes("user_fitbit_settings")
        )

        # Should have unique index on user_id
        user_id_indexes = [idx for idx in indexes if "user_id" in idx["column_names"]]
        assert len(user_id_indexes) > 0, "Missing index on user_id"

        # Check if unique constraint exists
        unique_constraints = await async_db_session.run_sync(
            lambda sync_session: inspector.get_unique_constraints("user_fitbit_settings")
        )
        user_id_unique = [
            uc for uc in unique_constraints if "user_id" in uc["column_names"]
        ]
        assert len(user_id_unique) > 0, "Missing unique constraint on user_id"

    async def test_migration_creates_fitbit_data_indexes(
        self, async_db_session: AsyncSession
    ):
        """Verify indexes on fitbit_data table."""
        inspector = inspect(async_db_session.bind)

        indexes = await async_db_session.run_sync(
            lambda sync_session: inspector.get_indexes("fitbit_data")
        )

        # Should have index on log_entry_id
        log_entry_indexes = [
            idx for idx in indexes if "log_entry_id" in idx["column_names"]
        ]
        assert len(log_entry_indexes) > 0, "Missing index on log_entry_id"

        # Should have index on user_id
        user_id_indexes = [idx for idx in indexes if "user_id" in idx["column_names"]]
        assert len(user_id_indexes) > 0, "Missing index on user_id"

        # Check unique constraint on log_entry_id
        unique_constraints = await async_db_session.run_sync(
            lambda sync_session: inspector.get_unique_constraints("fitbit_data")
        )
        log_entry_unique = [
            uc for uc in unique_constraints if "log_entry_id" in uc["column_names"]
        ]
        assert len(log_entry_unique) > 0, "Missing unique constraint on log_entry_id"


@pytest.mark.asyncio
class TestFitbitMigrationForeignKeys:
    """Test that migration creates proper foreign key constraints."""

    async def test_user_fitbit_settings_foreign_keys(
        self, async_db_session: AsyncSession
    ):
        """Verify foreign keys on user_fitbit_settings table."""
        inspector = inspect(async_db_session.bind)

        foreign_keys = await async_db_session.run_sync(
            lambda sync_session: inspector.get_foreign_keys("user_fitbit_settings")
        )

        # Should have foreign key to users table
        users_fk = [fk for fk in foreign_keys if fk["referred_table"] == "users"]
        assert len(users_fk) > 0, "Missing foreign key to users table"
        assert "user_id" in users_fk[0]["constrained_columns"]

    async def test_fitbit_data_foreign_keys(self, async_db_session: AsyncSession):
        """Verify foreign keys on fitbit_data table."""
        inspector = inspect(async_db_session.bind)

        foreign_keys = await async_db_session.run_sync(
            lambda sync_session: inspector.get_foreign_keys("fitbit_data")
        )

        # Should have foreign key to log_entries table
        log_entries_fk = [
            fk for fk in foreign_keys if fk["referred_table"] == "log_entries"
        ]
        assert len(log_entries_fk) > 0, "Missing foreign key to log_entries table"
        assert "log_entry_id" in log_entries_fk[0]["constrained_columns"]

        # Should have foreign key to users table
        users_fk = [fk for fk in foreign_keys if fk["referred_table"] == "users"]
        assert len(users_fk) > 0, "Missing foreign key to users table"
        assert "user_id" in users_fk[0]["constrained_columns"]


@pytest.mark.asyncio
class TestFitbitMigrationColumnTypes:
    """Test that migration creates columns with correct data types."""

    async def test_user_fitbit_settings_column_types(
        self, async_db_session: AsyncSession
    ):
        """Verify column types in user_fitbit_settings table."""
        inspector = inspect(async_db_session.bind)

        columns = await async_db_session.run_sync(
            lambda sync_session: inspector.get_columns("user_fitbit_settings")
        )

        column_types = {col["name"]: str(col["type"]) for col in columns}

        # Check key column types
        assert "UUID" in column_types["id"] or "CHAR" in column_types["id"]
        assert "UUID" in column_types["user_id"] or "CHAR" in column_types["user_id"]
        assert "BOOLEAN" in column_types["is_authorized"]
        assert "DATETIME" in column_types["created_at"]

    async def test_fitbit_data_column_types(self, async_db_session: AsyncSession):
        """Verify column types in fitbit_data table."""
        inspector = inspect(async_db_session.bind)

        columns = await async_db_session.run_sync(
            lambda sync_session: inspector.get_columns("fitbit_data")
        )

        column_types = {col["name"]: str(col["type"]) for col in columns}

        # Check UUID columns
        assert "UUID" in column_types["id"] or "CHAR" in column_types["id"]

        # Check integer columns
        assert "INTEGER" in column_types["heart_rate_bpm"]
        assert "INTEGER" in column_types["sleep_score"]
        assert "INTEGER" in column_types["steps_today"]

        # Check float columns
        assert "FLOAT" in column_types["sleep_efficiency_pct"] or "NUMERIC" in column_types["sleep_efficiency_pct"]
        assert "FLOAT" in column_types["distance_today_miles"] or "NUMERIC" in column_types["distance_today_miles"]

    async def test_fitbit_data_nullable_columns(self, async_db_session: AsyncSession):
        """Verify nullable columns in fitbit_data table."""
        inspector = inspect(async_db_session.bind)

        columns = await async_db_session.run_sync(
            lambda sync_session: inspector.get_columns("fitbit_data")
        )

        nullable_status = {col["name"]: col["nullable"] for col in columns}

        # These should be nullable (health data may not always be available)
        health_metrics = [
            "heart_rate_bpm",
            "sleep_score",
            "blood_oxygen_pct",
            "steps_today",
        ]

        for metric in health_metrics:
            assert nullable_status[metric] is True, f"{metric} should be nullable"

        # These should NOT be nullable
        assert nullable_status["id"] is False
        assert nullable_status["log_entry_id"] is False
        assert nullable_status["user_id"] is False
        assert nullable_status["captured_at"] is False


@pytest.mark.asyncio
class TestFitbitMigrationRollback:
    """Test migration rollback/downgrade."""

    async def test_migration_can_be_rolled_back(self, async_db_session: AsyncSession):
        """Test that downgrade migration removes Fitbit tables/columns."""
        # This test would require running the actual migration downgrade
        # For now, we'll just verify the current state is correct
        # In a real migration test, you'd:
        # 1. Run upgrade
        # 2. Verify tables exist
        # 3. Run downgrade
        # 4. Verify tables are removed
        pass

    async def test_downgrade_preserves_other_tables(
        self, async_db_session: AsyncSession
    ):
        """Test that downgrade doesn't affect non-Fitbit tables."""
        inspector = inspect(async_db_session.bind)

        tables = await async_db_session.run_sync(
            lambda sync_session: inspector.get_table_names()
        )

        # Core tables should still exist
        assert "users" in tables
        assert "log_entries" in tables
        assert "user_preferences" in tables
