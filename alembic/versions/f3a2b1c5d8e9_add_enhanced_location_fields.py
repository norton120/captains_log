"""Add enhanced location fields

Revision ID: bc172714604d
Revises: dcea7745b69b
Create Date: 2025-11-19 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a2b1c5d8e9'
down_revision: Union[str, Sequence[str], None] = 'dcea7745b69b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enhanced location fields."""
    # Add basic location columns if they don't exist
    op.add_column('log_entries', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('log_entries', sa.Column('location_name', sa.String(), nullable=True))
    
    # Add enhanced location fields
    op.add_column('log_entries', sa.Column('location_city', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('location_state', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('location_country', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('body_of_water', sa.String(), nullable=True))
    op.add_column('log_entries', sa.Column('nearest_port', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove enhanced location fields."""
    op.drop_column('log_entries', 'nearest_port')
    op.drop_column('log_entries', 'body_of_water')
    op.drop_column('log_entries', 'location_country')
    op.drop_column('log_entries', 'location_state')
    op.drop_column('log_entries', 'location_city')
    op.drop_column('log_entries', 'location_name')
    op.drop_column('log_entries', 'longitude')
    op.drop_column('log_entries', 'latitude')