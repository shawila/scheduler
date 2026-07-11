"""add pps_user_id and relax google token columns for broker-backed users

Revision ID: 005
Revises: 004
Create Date: 2026-07-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('pps_user_id', sa.String(100), nullable=True))
        batch_op.create_unique_constraint('uq_user_pps_user_id', ['pps_user_id'])
        batch_op.alter_column('token', existing_type=sa.String(500), nullable=True)
        batch_op.alter_column('refresh_token', existing_type=sa.String(500), nullable=True)
        batch_op.alter_column('token_uri', existing_type=sa.String(200), nullable=True)
        batch_op.alter_column('client_id', existing_type=sa.String(200), nullable=True)
        batch_op.alter_column('client_secret', existing_type=sa.String(200), nullable=True)
        batch_op.alter_column('scopes', existing_type=sa.Text(), nullable=True)


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('scopes', existing_type=sa.Text(), nullable=False)
        batch_op.alter_column('client_secret', existing_type=sa.String(200), nullable=False)
        batch_op.alter_column('client_id', existing_type=sa.String(200), nullable=False)
        batch_op.alter_column('token_uri', existing_type=sa.String(200), nullable=False)
        batch_op.alter_column('refresh_token', existing_type=sa.String(500), nullable=False)
        batch_op.alter_column('token', existing_type=sa.String(500), nullable=False)
        batch_op.drop_constraint('uq_user_pps_user_id', type_='unique')
        batch_op.drop_column('pps_user_id')
