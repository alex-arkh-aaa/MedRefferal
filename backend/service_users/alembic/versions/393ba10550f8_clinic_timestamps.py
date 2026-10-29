"""clinic timestamps

Revision ID: 393ba10550f8
Revises: 4e372c0c78b5
Create Date: 2026-10-29 16:06:47.176480

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '393ba10550f8'
down_revision: Union[str, None] = '4e372c0c78b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clinics",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "clinics",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("clinics", "updated_at")
    op.drop_column("clinics", "created_at")