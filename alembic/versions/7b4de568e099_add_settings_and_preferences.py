"""Add settings and preferences tables

Revision ID: 7b4de568e099
Revises: add_video_storage_fields
Create Date: 2025-11-21 07:59:30.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7b4de568e099'
down_revision = 'add_video_storage_fields'
branch_labels = None
depends_on = None


def upgrade():
    """Add settings and user_preferences tables, plus log types and weather fields."""

    # Create the LogType enum
    logtype_enum = sa.Enum('PERSONAL', 'SHIP', name='logtype')
    logtype_enum.create(op.get_bind(), checkfirst=True)

    # Create the MediaStorageMode enum
    mediastoragemode_enum = sa.Enum('S3_ONLY', 'LOCAL_WITH_S3', name='mediastoragemode')
    mediastoragemode_enum.create(op.get_bind(), checkfirst=True)
    
    # Add log_type column to log_entries
    op.add_column('log_entries', sa.Column('log_type', logtype_enum, nullable=False, server_default='SHIP'))
    
    # Add weather fields to log_entries
    op.add_column('log_entries', sa.Column('weather_air_temp_f', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_water_temp_f', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_wind_speed_kts', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_wind_direction_deg', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_wind_gust_kts', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_wave_height_ft', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_wave_period_sec', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_barometric_pressure_mb', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_visibility_nm', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_conditions', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_forecast', sa.Text(), nullable=True))
    op.add_column('log_entries', sa.Column('weather_captured_at', sa.DateTime(), nullable=True))
    
    # Create settings table
    op.create_table('settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('setting_type', sa.String(length=50), nullable=False, server_default='string'),
    )
    op.create_index(op.f('ix_settings_key'), 'settings', ['key'], unique=False)
    op.create_unique_constraint('uq_settings_key', 'settings', ['key'])
    
    # Create user_preferences table
    op.create_table('user_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('app_name', sa.String(length=255), nullable=False, server_default="Captain's Log"),
        sa.Column('vessel_name', sa.String(length=255), nullable=False, server_default='SV DEFIANT'),
        sa.Column('vessel_designation', sa.String(length=255), nullable=False, server_default='NCC-75633'),
        sa.Column('openai_model_whisper', sa.String(length=100), nullable=False, server_default='whisper-1'),
        sa.Column('openai_model_embedding', sa.String(length=100), nullable=False, server_default='text-embedding-3-small'),
        sa.Column('openai_model_chat', sa.String(length=100), nullable=False, server_default='gpt-4o-mini'),
        sa.Column('media_storage_mode', mediastoragemode_enum, nullable=False, server_default='S3_ONLY'),
        sa.Column('local_media_path', sa.String(length=500), nullable=True, server_default='./media'),
        sa.Column('max_audio_file_size', sa.Integer(), nullable=False, server_default='104857600'),  # 100MB
        sa.Column('max_video_file_size', sa.Integer(), nullable=False, server_default='1073741824'),  # 1GB
        sa.Column('allowed_audio_formats', sa.JSON(), nullable=False, server_default='["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]'),
        sa.Column('allowed_video_formats', sa.JSON(), nullable=False, server_default='["mp4", "webm", "mov", "avi"]'),
        sa.Column('default_page_size', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('max_page_size', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('enable_resilient_processing', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_network_retries', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('network_retry_base_delay', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('network_retry_max_delay', sa.Integer(), nullable=False, server_default='3600'),
        # AWS/S3 settings
        sa.Column('aws_access_key_id', sa.String(length=255), nullable=True),
        sa.Column('aws_secret_access_key', sa.String(length=255), nullable=True),
        sa.Column('aws_region', sa.String(length=50), nullable=True, server_default='us-east-2'),
        sa.Column('s3_bucket_name', sa.String(length=255), nullable=True),
        sa.Column('s3_audio_prefix', sa.String(length=100), nullable=False, server_default='audio/'),
        sa.Column('s3_video_prefix', sa.String(length=100), nullable=False, server_default='video/'),
        sa.Column('s3_presigned_url_expiry', sa.Integer(), nullable=False, server_default='3600'),
    )


def downgrade():
    """Remove settings, user_preferences tables, log types and weather fields."""
    
    # Drop tables
    op.drop_table('user_preferences')
    op.drop_table('settings')
    
    # Remove weather fields from log_entries
    op.drop_column('log_entries', 'weather_captured_at')
    op.drop_column('log_entries', 'weather_forecast')
    op.drop_column('log_entries', 'weather_conditions')
    op.drop_column('log_entries', 'weather_visibility_nm')
    op.drop_column('log_entries', 'weather_barometric_pressure_mb')
    op.drop_column('log_entries', 'weather_wave_period_sec')
    op.drop_column('log_entries', 'weather_wave_height_ft')
    op.drop_column('log_entries', 'weather_wind_gust_kts')
    op.drop_column('log_entries', 'weather_wind_direction_deg')
    op.drop_column('log_entries', 'weather_wind_speed_kts')
    op.drop_column('log_entries', 'weather_water_temp_f')
    op.drop_column('log_entries', 'weather_air_temp_f')
    
    # Remove log_type column
    op.drop_column('log_entries', 'log_type')
    
    # Drop the enums
    logtype_enum = sa.Enum('PERSONAL', 'SHIP', name='logtype')
    logtype_enum.drop(op.get_bind())
    
    mediastoragemode_enum = sa.Enum('S3_ONLY', 'LOCAL_WITH_S3', name='mediastoragemode')
    mediastoragemode_enum.drop(op.get_bind())