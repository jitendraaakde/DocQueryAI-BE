"""Add OAuth fields to users table

Revision ID: 8a2b3c4d5e6f
Revises: 165eb2d4077e
Create Date: 2024-12-16 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a2b3c4d5e6f'
down_revision = '165eb2d4077e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add OAuth fields to users table
    op.add_column('users', sa.Column('auth_provider', sa.String(50), nullable=True, server_default='local'))
    op.add_column('users', sa.Column('google_id', sa.String(255), nullable=True))
    
    # Create index on google_id
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)
    
    # Make hashed_password nullable for OAuth users
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.String(255),
                    nullable=True)


def downgrade() -> None:
    # Make hashed_password non-nullable again
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.String(255),
                    nullable=False)
    
    # Drop index and columns
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_column('users', 'google_id')
    op.drop_column('users', 'auth_provider')
