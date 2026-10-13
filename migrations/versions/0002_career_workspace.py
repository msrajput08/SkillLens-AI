"""Encrypted job tracker + resume drafts.
Revision ID: 0002
Revises: 0001
"""
from alembic import op
from sqlalchemy import inspect, Column, String, Text, DateTime, ForeignKey

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if 'applications' not in existing:
        op.create_table('applications',
            Column('id', String(40), primary_key=True),
            Column('user_id', String(40), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            Column('encrypted_data', Text(), nullable=False),
            Column('created_at', DateTime(), nullable=False),
            Column('updated_at', DateTime(), nullable=False))
        op.create_index('ix_applications_user_id', 'applications', ['user_id'])
    if 'resume_drafts' not in existing:
        op.create_table('resume_drafts',
            Column('id', String(40), primary_key=True),
            Column('user_id', String(40), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            Column('title', String(160), nullable=False),
            Column('encrypted_text', Text(), nullable=False),
            Column('created_at', DateTime(), nullable=False),
            Column('updated_at', DateTime(), nullable=False),
            Column('expires_at', DateTime(), nullable=False))
        op.create_index('ix_resume_drafts_user_id', 'resume_drafts', ['user_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade is unsupported; restore a verified backup.')
