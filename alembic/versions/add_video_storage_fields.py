"""Add video storage fields to log_entries

Revision ID: add_video_storage_fields
Revises: add_video_support
Create Date: 2024-11-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_video_storage_fields'
down_revision = 'add_video_support'
branch_labels = None
depends_on = None


def upgrade():
    """Add video storage fields to log_entries table."""
    # Add video storage columns
    op.add_column('log_entries', sa.Column('video_s3_key', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('video_local_path', sa.String(), nullable=True))


def downgrade():
    """Remove video storage fields from log_entries table."""
    # Remove video storage columns
    op.drop_column('log_entries', 'video_local_path')
    op.drop_column('log_entries', 'video_s3_key')