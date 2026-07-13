"""drop exchange_code table (direct-OAuth connect flow superseded by pps_auth broker)

Revision ID: 007
Revises: 006
Create Date: 2026-07-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('exchange_code')


def downgrade():
    op.create_table(
        'exchange_code',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(100), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
    )
