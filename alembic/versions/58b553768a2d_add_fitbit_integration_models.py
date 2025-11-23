"""Add Fitbit integration models

Revision ID: 58b553768a2d
Revises: add_user_support
Create Date: 2025-11-22 18:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '58b553768a2d'
down_revision: Union[str, Sequence[str], None] = 'aa817c3300c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Fitbit OAuth columns to user_preferences
    op.add_column('user_preferences', sa.Column('fitbit_oauth_client_id', sa.String(length=255), nullable=True))
    op.add_column('user_preferences', sa.Column('fitbit_oauth_client_secret', sa.String(length=255), nullable=True))

    # Create user_fitbit_settings table
    op.create_table('user_fitbit_settings',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('fitbit_user_id', sa.String(length=255), nullable=True),
    sa.Column('fitbit_device_id', sa.String(length=255), nullable=True),
    sa.Column('access_token', sa.Text(), nullable=True),
    sa.Column('refresh_token', sa.Text(), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_authorized', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_user_fitbit_settings_user_id'), 'user_fitbit_settings', ['user_id'], unique=True)

    # Create fitbit_data table
    op.create_table('fitbit_data',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('log_entry_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('heart_rate_bpm', sa.Integer(), nullable=True),
    sa.Column('resting_heart_rate_bpm', sa.Integer(), nullable=True),
    sa.Column('sleep_score', sa.Integer(), nullable=True),
    sa.Column('sleep_duration_minutes', sa.Integer(), nullable=True),
    sa.Column('sleep_efficiency_pct', sa.Float(), nullable=True),
    sa.Column('blood_oxygen_pct', sa.Float(), nullable=True),
    sa.Column('steps_today', sa.Integer(), nullable=True),
    sa.Column('calories_burned_today', sa.Integer(), nullable=True),
    sa.Column('active_minutes_today', sa.Integer(), nullable=True),
    sa.Column('distance_today_miles', sa.Float(), nullable=True),
    sa.Column('floors_climbed_today', sa.Integer(), nullable=True),
    sa.Column('vo2_max', sa.Float(), nullable=True),
    sa.Column('cardio_fitness_score', sa.Integer(), nullable=True),
    sa.Column('stress_score', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['log_entry_id'], ['log_entries.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('log_entry_id')
    )
    op.create_index(op.f('ix_fitbit_data_log_entry_id'), 'fitbit_data', ['log_entry_id'], unique=True)
    op.create_index(op.f('ix_fitbit_data_user_id'), 'fitbit_data', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop fitbit_data table
    op.drop_index(op.f('ix_fitbit_data_user_id'), table_name='fitbit_data')
    op.drop_index(op.f('ix_fitbit_data_log_entry_id'), table_name='fitbit_data')
    op.drop_table('fitbit_data')

    # Drop user_fitbit_settings table
    op.drop_index(op.f('ix_user_fitbit_settings_user_id'), table_name='user_fitbit_settings')
    op.drop_table('user_fitbit_settings')

    # Remove Fitbit OAuth columns from user_preferences
    op.drop_column('user_preferences', 'fitbit_oauth_client_secret')
    op.drop_column('user_preferences', 'fitbit_oauth_client_id')
