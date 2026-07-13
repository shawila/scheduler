"""add time_zone to pending_booking

Revision ID: 006
Revises: 005
Create Date: 2026-07-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pending_booking') as batch_op:
        batch_op.add_column(sa.Column('time_zone', sa.String(50), nullable=False, server_default='UTC'))


def downgrade():
    with op.batch_alter_table('pending_booking') as batch_op:
        batch_op.drop_column('time_zone')
