"""Standalone Razorpay Standard Checkout for TEST orders only.

This is intentionally separate from the existing recurring subscription flow.
A confirmed test payment NEVER changes user.tier or subscription entitlement.
"""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .saas import Base, Session, User, razorpay, require_user, throttle, utcnow

router = APIRouter(prefix='/api', tags=['standard-checkout'])

class CheckoutOrder(Base):
    __tablename__ = 'checkout_orders'
    order_id: Mapped[str] = mapped_column(String(90), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    receipt: Mapped[str] = mapped_column(String(40), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    status: Mapped[str] = mapped_column(String(20), default='created')
    payment_id: Mapped[str | None] = mapped_column(String(90), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class CreateOrderBody(BaseModel):
    amount: int = Field(ge=100, le=100000)
    currency: str = Field(default='INR', pattern=r'^INR$')

def configured_amount() -> int:
    try:
        amount = int(os.getenv('SKILLLENS_STANDARD_TEST_AMOUNT_PAISE', '100'))
    except ValueError as exc:
        raise HTTPException(503, 'Standard checkout amount is not configured correctly.') from exc
    if not 100 <= amount <= 100000:
        raise HTTPException(503, 'Configured test amount is outside allowed bounds.')
    return amount

def test_mode_enabled() -> bool:
    return (os.getenv('SKILLLENS_STANDARD_CHECKOUT_ENABLED', '').lower() == 'true'
            and os.getenv('RAZORPAY_KEY_ID', '').startswith('rzp_test_')
            and bool(os.getenv('RAZORPAY_KEY_SECRET', '')))

def require_test_mode():
    if not test_mode_enabled():
        raise HTTPException(503, 'Razorpay Standard Checkout test mode is not enabled.')

@router.get('/standard-checkout/config')
def checkout_config():
    enabled = test_mode_enabled()
    return {'enabled': enabled, 'mode': 'test', 'amount': configured_amount() if enabled else 100,
            'currency': 'INR', 'grants_pro': False,
            'description': 'One-time Razorpay test checkout; not a Pro subscription.'}

@router.post('/create-order')
async def create_order(data: CreateOrderBody, user: User = Depends(require_user)):
    require_test_mode()
    amount = configured_amount()
    # Never trust arbitrary browser-set prices. The server owns the product amount.
    if data.amount != amount or data.currency != 'INR':
        raise HTTPException(400, 'Requested amount/currency does not match the configured test product.')
    throttle('standard-checkout:create:' + user.id, limit=10, seconds=3600)
    receipt = 'sltest_' + secrets.token_hex(12)
    order = await razorpay('POST', 'orders', json={
        'amount': amount, 'currency': 'INR', 'receipt': receipt,
        'partial_payment': False, 'notes': {'purpose': 'skilllens_standard_test'},
    })
    order_id = order.get('id', '')
    if (not isinstance(order_id, str)
            or not re.fullmatch(r'order_[A-Za-z0-9]+', order_id)
            or order.get('amount') != amount
            or order.get('currency') != 'INR'
            or order.get('receipt') != receipt):
        raise HTTPException(502, 'Payment provider returned an invalid order.')
    with Session.begin() as db:
        db.add(CheckoutOrder(order_id=order_id, user_id=user.id,
                             receipt=receipt, amount=amount, currency='INR'))
    return {'order_id': order_id, 'amount': amount, 'currency': 'INR',
            'key_id': os.environ['RAZORPAY_KEY_ID'], 'email': user.email,
            'grants_pro': False}

@router.post('/verify-payment')
async def verify_payment(payload: dict, user: User = Depends(require_user)):
    require_test_mode()
    # Explicit 400 for missing/malformed fields, instead of Pydantic's default 422.
    if not isinstance(payload, dict):
        raise HTTPException(400, 'Invalid payment verification payload.')
    order_id = payload.get('razorpay_order_id')
    payment_id = payload.get('razorpay_payment_id')
    provided = payload.get('razorpay_signature')
    if (not isinstance(order_id, str) or not re.fullmatch(r'order_[A-Za-z0-9]+', order_id)
            or not isinstance(payment_id, str) or not re.fullmatch(r'pay_[A-Za-z0-9]+', payment_id)
            or not isinstance(provided, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', provided)):
        raise HTTPException(400, 'Missing or invalid payment verification fields.')
    with Session() as db:
        order = db.get(CheckoutOrder, order_id)
        if not order or order.user_id != user.id:
            raise HTTPException(404, 'Order not found.')
    secret = os.environ['RAZORPAY_KEY_SECRET'].encode()
    computed = hmac.new(secret, f'{order_id}|{payment_id}'.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, provided.lower()):
        raise HTTPException(400, 'Payment signature verification failed.')
    # Signed idempotent retries are safe; unsigned retries never report success.
    if order.status == 'captured':
        if order.payment_id != payment_id:
            raise HTTPException(400, 'Order is already associated with a different payment.')
        return {'verified': True, 'order_id': order_id, 'payment_id': payment_id,
                'amount': order.amount, 'currency': order.currency, 'grants_pro': False}

    # HMAC alone establishes callback authenticity, NOT whether money was captured.
    # Fetch the payment from Razorpay before recording success or granting anything.
    payment = await razorpay('GET', 'payments/' + payment_id)
    if (payment.get('id') != payment_id or payment.get('order_id') != order_id
            or payment.get('amount') != order.amount or payment.get('currency') != order.currency):
        raise HTTPException(400, 'Provider payment does not match this order.')
    if payment.get('status') != 'captured':
        raise HTTPException(409, 'Payment is not captured yet. Retry verification later.')
    with Session.begin() as db:
        current = db.scalar(select(CheckoutOrder).where(
            CheckoutOrder.order_id == order_id, CheckoutOrder.user_id == user.id).with_for_update())
        if not current:
            raise HTTPException(404, 'Order not found.')
        if current.payment_id not in (None, payment_id):
            raise HTTPException(409, 'Order has already been verified with another payment.')
        current.status = 'captured'
        current.payment_id = payment_id
        current.verified_at = utcnow()
    return {'verified': True, 'order_id': order_id, 'payment_id': payment_id,
            'amount': order.amount, 'currency': order.currency, 'grants_pro': False}
