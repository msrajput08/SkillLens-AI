"""Add user-owned one-time Razorpay TEST checkout orders.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, inspect

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if 'checkout_orders' in inspect(bind).get_table_names():
        return
    op.create_table(
        'checkout_orders',
        Column('order_id', String(90), primary_key=True),
        Column('user_id', String(40), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        Column('receipt', String(40), unique=True, nullable=False),
        Column('amount', Integer(), nullable=False),
        Column('currency', String(3), nullable=False),
        Column('status', String(20), nullable=False),
        Column('payment_id', String(90), unique=True, nullable=True),
        Column('created_at', DateTime(), nullable=False),
        Column('verified_at', DateTime(), nullable=True),
    )
    op.create_index('ix_checkout_orders_user_id', 'checkout_orders', ['user_id'])

def downgrade():
    raise RuntimeError('Checkout order records are not deleted by automatic rollback.')
