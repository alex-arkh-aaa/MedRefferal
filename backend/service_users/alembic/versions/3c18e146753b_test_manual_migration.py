"""test manual migration

Revision ID: 3c18e146753b
Revises: 31c11f74426c
Create Date: 2026-07-28 14:24:37.384421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c18e146753b'
down_revision: Union[str, None] = '31c11f74426c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'is_active')


def downgrade() -> None:
    op.add_column('users', sa.Column('is_active', sa.Boolean()))
