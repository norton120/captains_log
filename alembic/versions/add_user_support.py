"""Add user support - users table and user_id foreign key on log_entries

Revision ID: add_user_support
Revises: 31b07ed07a1e
Create Date: 2025-11-22 12:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_user_support'
down_revision: Union[str, Sequence[str], None] = '31b07ed07a1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Create a generic user
    from sqlalchemy import text
    op.execute(text("""
        INSERT INTO users (id, username, email, created_at)
        VALUES (gen_random_uuid(), 'generic_user', 'generic@captainslog.local', NOW())
        ON CONFLICT DO NOTHING
    """))

    # Add user_id column to log_entries (nullable initially)
    op.add_column('log_entries', sa.Column('user_id', sa.UUID(), nullable=True))

    # Set all existing log_entries to belong to the generic user
    op.execute(text("""
        UPDATE log_entries
        SET user_id = (SELECT id FROM users WHERE username = 'generic_user')
        WHERE user_id IS NULL
    """))

    # Now make user_id non-nullable and add foreign key constraint
    op.alter_column('log_entries', 'user_id', nullable=False)
    op.create_index(op.f('ix_log_entries_user_id'), 'log_entries', ['user_id'])
    op.create_foreign_key(
        'fk_log_entries_user_id_users',
        'log_entries', 'users',
        ['user_id'], ['id'],
        ondelete='RESTRICT'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key and index from log_entries
    op.drop_constraint('fk_log_entries_user_id_users', 'log_entries', type_='foreignkey')
    op.drop_index(op.f('ix_log_entries_user_id'), table_name='log_entries')
    op.drop_column('log_entries', 'user_id')

    # Drop indexes from users table
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_username'), table_name='users')

    # Drop users table
    op.drop_table('users')
