"""add audio_local_path column

Revision ID: add_audio_local_path
Revises: f3a2b1c5d8e9
Create Date: 2025-01-20 20:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_audio_local_path'
down_revision: Union[str, None] = 'f3a2b1c5d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add audio_local_path column
    op.add_column('log_entries', sa.Column('audio_local_path', sa.String(), nullable=True))
    
    # Make audio_s3_key nullable since we now support local-only storage
    op.alter_column('log_entries', 'audio_s3_key', nullable=True)


def downgrade() -> None:
    # Remove audio_local_path column
    op.drop_column('log_entries', 'audio_local_path')
    
    # Make audio_s3_key non-nullable again
    op.alter_column('log_entries', 'audio_s3_key', nullable=False)