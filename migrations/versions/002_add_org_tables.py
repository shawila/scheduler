"""rename customer to user, add org tables and user.api_token

Revision ID: 002
Revises: 001
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Rename customer to user if it exists
    ctx = op.get_context()
    if ctx.bind.dialect.has_table(ctx.bind, 'customer'):
        op.rename_table('customer', 'user')

    # Create user table if it doesn't exist
    if not ctx.bind.dialect.has_table(ctx.bind, 'user'):
        op.create_table(
            'user',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(120), nullable=False, unique=True),
            sa.Column('token', sa.String(500), nullable=False),
            sa.Column('refresh_token', sa.String(500), nullable=False),
            sa.Column('token_uri', sa.String(200), nullable=False),
            sa.Column('client_id', sa.String(200), nullable=False),
            sa.Column('client_secret', sa.String(200), nullable=False),
            sa.Column('scopes', sa.Text(), nullable=False),
            sa.Column('api_token', sa.String(100), nullable=True, unique=True),
            sa.PrimaryKeyConstraint('id'),
        )
    else:
        # Add api_token column if table exists but column doesn't
        with op.batch_alter_table('user') as batch_op:
            batch_op.add_column(sa.Column('api_token', sa.String(100), nullable=True))
            batch_op.create_unique_constraint('uq_user_api_token', ['api_token'])

    op.create_table(
        'organization',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('google_calendar_id', sa.String(300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'organization_member',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organization.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )

    op.create_table(
        'organization_invite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('invited_email', sa.String(120), nullable=False),
        sa.Column('token', sa.String(100), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organization.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
        sa.UniqueConstraint('org_id', 'invited_email', name='uq_org_invite_org_email'),
    )


def downgrade():
    op.drop_table('organization_invite')
    op.drop_table('organization_member')
    op.drop_table('organization')

    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_constraint('uq_user_api_token', type_='unique')
        batch_op.drop_column('api_token')

    op.rename_table('user', 'customer')
