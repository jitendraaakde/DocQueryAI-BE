"""add action_items column to documents

Revision ID: a1b2c3d4e5f6
Revises: 0116040413a7
Create Date: 2024-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0116040413a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add action_items column to documents table
    op.add_column('documents', sa.Column('action_items', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove action_items column from documents table
    op.drop_column('documents', 'action_items')
