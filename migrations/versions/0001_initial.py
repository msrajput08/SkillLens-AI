"""Initial commercial SaaS schema.

Revision ID: 0001
Revises:
"""
from alembic import op
from app.saas import Base
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    # Intentionally blocks destructive downgrade; make backup and migrate forward.
    raise RuntimeError('Destructive downgrade is not supported. Restore a verified database backup.')
