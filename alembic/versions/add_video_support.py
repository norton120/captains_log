"""Add video support fields to log_entries

Revision ID: add_video_support
Revises: add_audio_local_path
Create Date: 2024-11-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_video_support'
down_revision = 'add_audio_local_path'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the MediaType enum
    media_type_enum = sa.Enum('AUDIO', 'VIDEO', name='mediatype')
    media_type_enum.create(op.get_bind())
    
    # Add new columns to log_entries
    op.add_column('log_entries', sa.Column('media_type', media_type_enum, nullable=False, default='AUDIO'))
    op.add_column('log_entries', sa.Column('original_filename', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('is_video_source', sa.Boolean(), nullable=False, default=False))


def downgrade() -> None:
    # Remove the new columns
    op.drop_column('log_entries', 'is_video_source')
    op.drop_column('log_entries', 'original_filename')
    op.drop_column('log_entries', 'media_type')
    
    # Drop the MediaType enum
    media_type_enum = sa.Enum('AUDIO', 'VIDEO', name='mediatype')
    media_type_enum.drop(op.get_bind())