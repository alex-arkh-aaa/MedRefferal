"""drop registrations

Revision ID: 00ebc10d1104
Revises: 393ba10550f8
Create Date: 2026-10-29 17:39:37.302922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00ebc10d1104'
down_revision: Union[str, None] = '393ba10550f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_registrations_id", table_name="registrations")
    op.drop_index("ix_registrations_email", table_name="registrations")
    op.drop_index("ix_registrations_clinic_id", table_name="registrations")
    op.drop_index("ix_registrations_admin_id", table_name="registrations")
    op.drop_index("ix_registrations_agent_id", table_name="registrations")
    op.drop_table("registrations")


def downgrade() -> None:
    pass
