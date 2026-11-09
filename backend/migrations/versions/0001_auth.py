"""Initial authentication tables."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('created_at', sa.Integer(), nullable=False))
    op.create_table('identities', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False), sa.UniqueConstraint('provider', 'subject'))
    op.create_table('pending_signups', sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False), sa.Column('name', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False), sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False), sa.Column('sent_at', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False), sa.Column('resends', sa.Integer(), nullable=False))
    op.create_index('ix_pending_signups_expires_at', 'pending_signups', ['expires_at'])
    op.create_table('login_sessions', sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False))
    op.create_index('ix_login_sessions_expires_at', 'login_sessions', ['expires_at'])
    op.create_table('rate_buckets', sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('count', sa.Integer(), nullable=False), sa.Column('expires_at', sa.Integer(), nullable=False))
    op.create_index('ix_rate_buckets_expires_at', 'rate_buckets', ['expires_at'])


def downgrade():
    for table in ['rate_buckets', 'login_sessions', 'pending_signups', 'identities', 'users']:
        op.drop_table(table)
