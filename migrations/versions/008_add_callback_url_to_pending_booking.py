"""add callback_url to pending_booking

Revision ID: 008
Revises: 007
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pending_booking') as batch_op:
        batch_op.add_column(sa.Column('callback_url', sa.String(500), nullable=True))


def downgrade():
    with op.batch_alter_table('pending_booking') as batch_op:
        batch_op.drop_column('callback_url')
