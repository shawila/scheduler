"""add exchange_code table for hatan connect flow

Revision ID: 004
Revises: 003
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'exchange_code',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(100), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('exchange_code')
