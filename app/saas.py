"""SkillLens commercial SaaS backend: first-party auth, quota, encrypted opt-in history,
Razorpay subscription webhooks. See SECURITY.md for threat model and deployment gates.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import httpx
from argon2 import PasswordHasher, exceptions as argon_error
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, delete, func, select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ENV = os.getenv('SKILLLENS_ENV', 'development').lower()
PROD = ENV == 'production'
NO_CARD_BETA = PROD and os.getenv('SKILLLENS_LAUNCH_MODE', '').lower() == 'render_beta'
SITE_URL = os.getenv('SKILLLENS_SITE_URL', 'http://localhost:8000').rstrip('/')
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///./skilllens_dev.db')
FERNET_KEY = os.getenv('SKILLLENS_DATA_KEY', '')
COOKIE_NAME = 'skilllens_session'
AUTH_DAYS = 14
FREE_LIMITS = {'analyze': 5, 'rewrite': 3}
PRO_LIMITS = {'analyze': 200, 'rewrite': 100}
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
# Fixed dummy password hash avoids allocating TWO expensive Argon2 computations
# for every login attempt against an unknown email. Never generate per request.
DUMMY_PASSWORD_HASH = '$argon2id$v=19$m=65536,t=3,p=2$Bq80fBSCjjLTStdpth09xA$kUz6r67NTenIvGeJOTyDpqsrheVQk5s3Yoh/ebzl/6g'
logger = logging.getLogger('skilllens.email')

if PROD:
    required = {'DATABASE_URL': DB_URL if 'DATABASE_URL' in os.environ else '',
                'SKILLLENS_DATA_KEY': FERNET_KEY,
                'SMTP_FROM': os.getenv('SMTP_FROM', ''),
                'LEGAL_OPERATOR': os.getenv('LEGAL_OPERATOR', ''),
                'LEGAL_CONTACT_EMAIL': os.getenv('LEGAL_CONTACT_EMAIL', ''),
                'LEGAL_REVIEWED': os.getenv('LEGAL_REVIEWED', '') if os.getenv('LEGAL_REVIEWED') == 'yes' else '',
                'LEGAL_POSTAL_ADDRESS': os.getenv('LEGAL_POSTAL_ADDRESS', '')}
    if not NO_CARD_BETA:
        required.update({k: os.getenv(k, '') for k in (
            'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', 'RAZORPAY_PLAN_ID',
            'RAZORPAY_WEBHOOK_SECRET', 'SKILLLENS_PRO_PRICE_INR', 'SKILLLENS_CLAMAV_ADDR')})
    if not os.getenv('BREVO_API_KEY'):
        required['SMTP_HOST'] = os.getenv('SMTP_HOST', '')
    if NO_CARD_BETA and not os.getenv('BREVO_API_KEY'):
        raise RuntimeError('Render beta requires Brevo HTTPS API email; SMTP is blocked by Render Free.')
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError('Production configuration missing: ' + ', '.join(missing))
    if any('REPLACE' in v or 'example.com' in v for v in required.values()) or 'REPLACE' in DB_URL or 'example.com' in SITE_URL:
        raise RuntimeError('Replace all example credentials, placeholder domains and operator details before production.')
    if not DB_URL.startswith('postgresql+') or not SITE_URL.startswith('https://'):
        raise RuntimeError('Production requires PostgreSQL and an HTTPS SKILLLENS_SITE_URL')
    if not os.getenv('BREVO_API_KEY') and (not os.getenv('SMTP_USERNAME') or not os.getenv('SMTP_PASSWORD')):
        raise RuntimeError('Production email requires SMTP credentials or BREVO_API_KEY')
if FERNET_KEY:
    cipher = Fernet(FERNET_KEY.encode())
else:
    # Development-only persistent key. Production NEVER generates a secret at boot.
    key_path = Path(os.getenv('SKILLLENS_DEV_KEY_FILE', './.skilllens_dev_key'))
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.exists():
        try:
            fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(Fernet.generate_key())
        except FileExistsError:
            pass
    cipher = Fernet(key_path.read_bytes())
engine = create_engine(DB_URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if DB_URL.startswith('sqlite') else {})
Session = sessionmaker(engine, expire_on_commit=False)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(16), default='free')
    provider_subscription_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    subscription_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SessionToken(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class OneTimeToken(Base):
    __tablename__ = 'one_time_tokens'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'))
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Usage(Base):
    __tablename__ = 'usage'
    __table_args__ = (UniqueConstraint('user_id', 'period', 'feature'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'))
    period: Mapped[str] = mapped_column(String(7))
    feature: Mapped[str] = mapped_column(String(20))
    used: Mapped[int] = mapped_column(Integer, default=0)


class SavedReport(Base):
    __tablename__ = 'saved_reports'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    encrypted_report: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Application(Base):
    """User-private encrypted job tracker item. No plaintext role/company indexing."""
    __tablename__ = 'applications'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    encrypted_data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ResumeDraft(Base):
    """User-private encrypted resume builder draft. Drafts expire after 90 days."""
    __tablename__ = 'resume_drafts'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    encrypted_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class WebhookEvent(Base):
    __tablename__ = 'webhook_events'
    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RateWindow(Base):
    __tablename__ = 'rate_windows'
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


def init_db():
    # Schema bootstrap for fresh installations. For existing production databases,
    # apply reviewed migrations before deploying incompatible schema changes.
    Base.metadata.create_all(engine)
    if NO_CARD_BETA:
        # Render Free has no always-on background worker; purge expired records on wake.
        from .cleanup import purge
        purge()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(key: str, limit: int, seconds: int):
    """Persistent fixed-window throttling. Needs an upstream WAF for distributed flood protection."""
    key = digest(key)
    now = utcnow()
    with Session.begin() as db:
        if engine.dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        stmt = insert(RateWindow).values(key=key, count=0, expires_at=now + timedelta(seconds=seconds))
        db.execute(stmt.on_conflict_do_nothing(index_elements=['key']))
        # Concurrent increment guarded in SQL; reset stale window atomically.
        db.execute(update(RateWindow).where(RateWindow.key == key, RateWindow.expires_at <= now)
                   .values(count=0, expires_at=now + timedelta(seconds=seconds)))
        updated = db.execute(update(RateWindow).where(RateWindow.key == key, RateWindow.count < limit)
                             .values(count=RateWindow.count + 1))
        if updated.rowcount == 0:
            raise HTTPException(429, 'Too many attempts. Please try again later.')


def identity_email(raw: str) -> str:
    return raw.strip().lower()


def make_login_cookie(response: Response, token: str):
    response.set_cookie(COOKIE_NAME, token, max_age=AUTH_DAYS * 86400, secure=PROD,
                        httponly=True, samesite='lax', path='/')


def session_auth(request: Request, check_csrf: bool = False):
    token = request.cookies.get(COOKIE_NAME, '')
    if not token:
        raise HTTPException(401, 'Sign in to continue.')
    with Session() as db:
        obj = db.get(SessionToken, digest(token))
        if not obj or obj.expires_at <= utcnow():
            raise HTTPException(401, 'Your session has expired. Sign in again.')
        u = db.get(User, obj.user_id)
        if not u or not u.verified:
            raise HTTPException(403, 'Verify your email before continuing.')
        if check_csrf:
            csrf = request.headers.get('x-csrf-token', '')
            if not csrf or not hmac.compare_digest(digest(csrf), obj.csrf_hash):
                raise HTTPException(403, 'Security token missing or invalid. Refresh the page.')
        return u


def require_user(request: Request) -> User:
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        session_auth(request, check_csrf=True)
    return session_auth(request)


def send_email(to: str, subject: str, body: str):
    brevo_api_key = os.getenv('BREVO_API_KEY', '')
    if brevo_api_key:
        try:
            response = httpx.post(
                'https://api.brevo.com/v3/smtp/email',
                headers={'api-key': brevo_api_key, 'accept': 'application/json'},
                json={'sender': {'email': os.environ['SMTP_FROM'], 'name': 'SkillLens'},
                      'to': [{'email': to}], 'subject': subject, 'textContent': body},
                timeout=12.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Never log addresses, API keys, request bodies, or response bodies.
            logger.warning('Transactional email provider rejected request (HTTP %d).', exc.response.status_code)
            raise HTTPException(503, 'Email delivery unavailable. Please try again later.') from exc
        except httpx.RequestError as exc:
            logger.warning('Transactional email provider network error (%s).', type(exc).__name__)
            raise HTTPException(503, 'Email delivery unavailable. Please try again later.') from exc
        return
    host = os.getenv('SMTP_HOST', '')
    if not host:
        if PROD:
            raise HTTPException(503, 'Email service unavailable.')
        return
    msg = EmailMessage()
    msg['To'], msg['From'], msg['Subject'] = to, os.environ['SMTP_FROM'], subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587')), timeout=12) as mail:
        mail.starttls()
        mail.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        mail.send_message(msg)


def create_one_time(user_id: str, purpose: str) -> str:
    token = secrets.token_urlsafe(40)
    with Session.begin() as db:
        db.add(OneTimeToken(token_hash=digest(token), user_id=user_id, purpose=purpose,
                            expires_at=utcnow() + timedelta(minutes=30)))
    return token


def usage_info(user: User) -> dict:
    period = utcnow().strftime('%Y-%m')
    limits = PRO_LIMITS if user.tier == 'pro' else FREE_LIMITS
    with Session() as db:
        records = db.scalars(select(Usage).where(Usage.user_id == user.id, Usage.period == period)).all()
    current = {record.feature: record.used for record in records}
    return {k: {'used': current.get(k, 0), 'limit': v} for k, v in limits.items()}


def ensure_quota(user: User, feature: str):
    """Reject exhausted monthly quotas before expensive NLP/model inference.

    A separate atomic charge after successful work remains the source of truth;
    two concurrent requests cannot both claim the last credit.
    """
    limits = PRO_LIMITS if user.tier == 'pro' else FREE_LIMITS
    if feature not in limits:
        raise HTTPException(400, 'Unknown feature')
    period = utcnow().strftime('%Y-%m')
    with Session() as db:
        used = db.scalar(select(Usage.used).where(
            Usage.user_id == user.id, Usage.period == period, Usage.feature == feature)) or 0
    if used >= limits[feature]:
        raise HTTPException(402, f'{feature.title()} monthly limit reached. Upgrade your plan to continue.')


def charge(user: User, feature: str):
    limits = PRO_LIMITS if user.tier == 'pro' else FREE_LIMITS
    if feature not in limits:
        raise HTTPException(400, 'Unknown feature')
    period = utcnow().strftime('%Y-%m')
    with Session.begin() as db:
        if engine.dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        db.execute(insert(Usage).values(user_id=user.id, period=period, feature=feature, used=0)
                   .on_conflict_do_nothing(index_elements=['user_id', 'period', 'feature']))
        q = update(Usage).where(Usage.user_id == user.id, Usage.period == period,
                                Usage.feature == feature, Usage.used < limits[feature])
        result = db.execute(q.values(used=Usage.used + 1))
        if not result.rowcount:
            raise HTTPException(402, f'{feature.title()} monthly limit reached. Upgrade your plan to continue.')


def public_user(user: User):
    return {'email': user.email, 'verified': user.verified, 'tier': user.tier,
            'billing_status': user.subscription_status, 'usage': usage_info(user)}


router = APIRouter(prefix='/api')


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


@router.post('/auth/register')
def register(data: Credentials, request: Request):
    email = identity_email(data.email)
    throttle('register:' + (request.client.host if request.client else 'unknown'), 30, 3600)
    throttle('register-email:' + email, 3, 3600)
    if not re.search(r'[A-Za-z]', data.password) or not re.search(r'\d', data.password):
        raise HTTPException(422, 'Password needs letters and a number.')
    user = User(id=secrets.token_hex(16), email=email, password_hash=ph.hash(data.password),
                verified=(not PROD and not os.getenv('SMTP_HOST')))
    with Session.begin() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, 'Account already exists. Sign in or reset your password.')
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            raise HTTPException(409, 'Account already exists.')
    if not user.verified:
        token = create_one_time(user.id, 'verify')
        send_email(email, 'Verify your SkillLens account', f'Complete verification:\n{SITE_URL}/?verify={token}\n\nLink expires in 30 minutes.')
    return {'message': 'Account created. Verify the link emailed to you.' if not user.verified else 'Development account created. Sign in now.'}


@router.get('/auth/verify')
def verify(token: str):
    with Session.begin() as db:
        entry = db.get(OneTimeToken, digest(token))
        if not entry or entry.purpose != 'verify' or entry.expires_at <= utcnow():
            raise HTTPException(400, 'Invalid or expired verification link.')
        u = db.get(User, entry.user_id)
        if not u:
            raise HTTPException(404, 'Account not found.')
        u.verified = True
        db.delete(entry)
    return {'message': 'Email verified. You can sign in.'}


@router.post('/auth/login')
def login(data: Credentials, request: Request, response: Response):
    email = identity_email(data.email)
    throttle('login-ip:' + (request.client.host if request.client else ''), 50, 3600)
    throttle('login:' + email, 10, 900)
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.email == email))
        try:
            if not user:
                # Similar verification work for unknown accounts, without hashing
                # a fresh dummy secret first (which doubles Argon2 CPU/memory).
                try:
                    ph.verify(DUMMY_PASSWORD_HASH, data.password)
                except argon_error.VerificationError:
                    pass
                raise HTTPException(401, 'Incorrect email or password.')
            ph.verify(user.password_hash, data.password)
        except (argon_error.VerifyMismatchError, argon_error.VerificationError):
            raise HTTPException(401, 'Incorrect email or password.')
        if not user.verified:
            raise HTTPException(403, 'Verify your email before signing in.')
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        db.add(SessionToken(token_hash=digest(token), csrf_hash=digest(csrf), user_id=user.id,
                            expires_at=utcnow() + timedelta(days=AUTH_DAYS)))
    make_login_cookie(response, token)
    return {'user': public_user(user), 'csrf': csrf}


@router.get('/auth/me')
def me(request: Request):
    token = request.cookies.get(COOKIE_NAME, '')
    if not token:
        raise HTTPException(401, 'Not signed in.')
    # CSRF cookie-independent state: returned only on first login, or freshly rotated on GET /me
    # /me is same-origin and no CORS. Rotation invalidates older forms/tabs.
    with Session.begin() as db:
        session = db.get(SessionToken, digest(token))
        if not session or session.expires_at <= utcnow():
            raise HTTPException(401, 'Session expired.')
        user = db.get(User, session.user_id)
        if not user or not user.verified:
            raise HTTPException(401, 'Account not verified.')
        csrf = secrets.token_urlsafe(32)
        session.csrf_hash = digest(csrf)
    return {'user': public_user(user), 'csrf': csrf}


@router.post('/auth/logout')
def logout(request: Request, response: Response, _=Depends(require_user)):
    with Session.begin() as db:
        db.execute(delete(SessionToken).where(SessionToken.token_hash == digest(request.cookies.get(COOKIE_NAME, ''))))
    response.delete_cookie(COOKIE_NAME, path='/', secure=PROD, httponly=True, samesite='lax')
    return {'ok': True}


class EmailOnly(BaseModel):
    email: EmailStr


@router.post('/auth/forgot-password')
def forgot(data: EmailOnly, request: Request):
    email = identity_email(data.email)
    throttle('reset-ip:' + (request.client.host if request.client else ''), 8, 3600)
    throttle('reset-email:' + email, 3, 3600)
    with Session() as db:
        user = db.scalar(select(User).where(User.email == email))
    if user:
        token = create_one_time(user.id, 'reset')
        send_email(email, 'Reset your SkillLens password', f'Reset your password:\n{SITE_URL}/?reset={token}\n\nLink expires in 30 minutes.')
    return {'message': 'If this account exists, a reset link has been sent.'}


class ResetBody(BaseModel):
    token: str = Field(min_length=30, max_length=200)
    new_password: str = Field(min_length=12, max_length=128)



@router.post('/auth/resend-verification')
def resend_verification(data: EmailOnly, request: Request):
    email = identity_email(data.email)
    throttle('resend-ip:' + (request.client.host if request.client else ''), 12, 3600)
    throttle('resend-email:' + email, 3, 3600)
    with Session() as db:
        u = db.scalar(select(User).where(User.email == email))
    if u and not u.verified:
        token = create_one_time(u.id, 'verify')
        send_email(email, 'Verify your SkillLens account',
                   f'Complete verification:\n{SITE_URL}/?verify={token}\n\nLink expires in 30 minutes.')
    return {'message': 'If that account needs verification, a new link has been sent.'}

@router.post('/auth/reset-password')
def reset(data: ResetBody, request: Request):
    throttle('reset-use:' + (request.client.host if request.client else ''), 12, 3600)
    if not re.search('[A-Za-z]', data.new_password) or not re.search(r'\d', data.new_password):
        raise HTTPException(422, 'Password needs letters and a number.')
    with Session.begin() as db:
        entry = db.get(OneTimeToken, digest(data.token))
        if not entry or entry.purpose != 'reset' or entry.expires_at <= utcnow():
            raise HTTPException(400, 'Invalid or expired reset link.')
        u = db.get(User, entry.user_id)
        u.password_hash = ph.hash(data.new_password)
        db.execute(delete(SessionToken).where(SessionToken.user_id == u.id))
        db.delete(entry)
    return {'message': 'Password updated. Sign in again.'}


@router.get('/usage')
def usage(user: User = Depends(require_user)):
    return {'tier': user.tier, 'features': usage_info(user)}


class SaveBody(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    report: dict


@router.post('/reports')
def save_report(data: SaveBody, user: User = Depends(require_user)):
    serialized = json.dumps(data.report, ensure_ascii=False)
    if len(serialized.encode()) > 150000:
        raise HTTPException(413, 'Report too large.')
    with Session.begin() as db:
        # Serialize save operations for one user on PostgreSQL, preventing the
        # concurrent-request race around the maximum saved report count.
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
        existing = db.scalar(select(func.count()).select_from(SavedReport).where(SavedReport.user_id == user.id,
                                                                                SavedReport.expires_at > utcnow()))
        if existing >= (100 if user.tier == 'pro' else 5):
            raise HTTPException(402, 'Saved report limit reached. Delete an old report or upgrade.')
        item = SavedReport(id=secrets.token_hex(16), user_id=user.id, title=data.title,
                           encrypted_report=cipher.encrypt(serialized.encode()).decode(),
                           expires_at=utcnow() + timedelta(days=30))
        db.add(item)
    return {'id': item.id, 'message': 'Report encrypted and saved for 30 days.'}


@router.get('/reports')
def list_reports(user: User = Depends(require_user)):
    with Session() as db:
        entries = db.scalars(select(SavedReport).where(SavedReport.user_id == user.id,
                                                      SavedReport.expires_at > utcnow())
                             .order_by(SavedReport.created_at.desc()).limit(100)).all()
    return [{'id': x.id, 'title': x.title, 'created_at': x.created_at.isoformat() + 'Z',
             'expires_at': x.expires_at.isoformat() + 'Z'} for x in entries]


@router.get('/reports/{report_id}')
def get_report(report_id: str, user: User = Depends(require_user)):
    with Session() as db:
        entry = db.get(SavedReport, report_id)
        if not entry or entry.user_id != user.id or entry.expires_at < utcnow():
            raise HTTPException(404, 'Report not found.')
        try:
            data = json.loads(cipher.decrypt(entry.encrypted_report.encode()).decode())
        except (InvalidToken, ValueError):
            raise HTTPException(503, 'Encryption key changed. Cannot decrypt this saved report.')
    return data


@router.delete('/reports/{report_id}')
def delete_report(report_id: str, user: User = Depends(require_user)):
    with Session.begin() as db:
        result = db.execute(delete(SavedReport).where(SavedReport.id == report_id,
                                                     SavedReport.user_id == user.id))
        if result.rowcount == 0:
            raise HTTPException(404, 'Report not found.')
    return {'ok': True}


@router.get('/billing/config')
def billing_config():
    return {'provider': 'razorpay', 'enabled': not NO_CARD_BETA and bool(os.getenv('RAZORPAY_KEY_ID') and os.getenv('RAZORPAY_PLAN_ID')),
            'plan': 'Pro', 'currency': 'INR', 'price': os.getenv('SKILLLENS_PRO_PRICE_INR') or None,
            'message': 'Pricing is displayed in Razorpay Checkout. Set your plan in the merchant dashboard.'}


async def razorpay(method: str, path: str, **kwargs):
    key, secret = os.getenv('RAZORPAY_KEY_ID', ''), os.getenv('RAZORPAY_KEY_SECRET', '')
    if not key or not secret:
        raise HTTPException(503, 'Billing is not configured.')
    # Do not log requests, credentials, response descriptions or payment identifiers.
    billing_log = logging.getLogger('skilllens.billing')
    operation = path.split('/')[0]
    try:
        async with httpx.AsyncClient(timeout=15.0, auth=(key, secret)) as client:
            resp = await client.request(method, 'https://api.razorpay.com/v1/' + path, **kwargs)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        code = 'unknown'
        try:
            raw = exc.response.json().get('error', {}).get('code', '')
            if isinstance(raw, str) and re.fullmatch(r'[A-Z_]{2,60}', raw):
                code = raw
        except (ValueError, AttributeError, TypeError):
            pass
        billing_log.warning('Razorpay %s %s rejected request: HTTP %d (%s)',
                            method, operation, status, code)
        if status == 401:
            # Upstream authentication failure: use 502 to avoid signing out the
            # logged-in customer (the client handles its own 401 as session loss).
            raise HTTPException(502, 'Razorpay Test Mode credentials were rejected (upstream 401). Check the matching key ID and secret.') from exc
        if status == 403:
            raise HTTPException(502, 'Razorpay account is not permitted to create this order (upstream 403).') from exc
        if status == 400:
            raise HTTPException(502, 'Razorpay rejected the order request (upstream 400). Check the account and order configuration.') from exc
        if status == 429:
            raise HTTPException(503, 'Razorpay request limit reached. Try again later.') from exc
        raise HTTPException(502, 'Payment provider request failed. Try again later.') from exc
    except httpx.RequestError as exc:
        billing_log.warning('Razorpay %s %s network failure (%s)',
                            method, operation, type(exc).__name__)
        raise HTTPException(502, 'Could not connect to Razorpay. Try again later.') from exc
    except ValueError as exc:
        billing_log.warning('Razorpay %s %s returned invalid JSON', method, operation)
        raise HTTPException(502, 'Payment provider returned an invalid response.') from exc


@router.post('/billing/checkout')
async def billing_checkout(user: User = Depends(require_user)):
    if NO_CARD_BETA:
        raise HTTPException(503, 'Payments are not enabled during the free beta.')
    if user.tier == 'pro':
        raise HTTPException(409, 'You already have an active Pro subscription.')
    plan = os.getenv('RAZORPAY_PLAN_ID', '')
    if not plan:
        raise HTTPException(503, 'Merchant billing plan is not configured.')
    # Fail closed when the actual merchant plan differs from the advertised amount.
    price = os.getenv('SKILLLENS_PRO_PRICE_INR', '')
    if price:
        try:
            advertised_paise = int(Decimal(price) * 100)
        except (InvalidOperation, ValueError):
            raise HTTPException(503, 'Merchant price configuration is invalid.')
        actual_plan = await razorpay('GET', f'plans/{plan}')
        if (actual_plan.get('item', {}).get('amount') != advertised_paise
                or actual_plan.get('item', {}).get('currency') != 'INR'
                or actual_plan.get('period') != 'monthly'
                or actual_plan.get('interval') != 1):
            raise HTTPException(503, 'Billing plan and advertised monthly price do not match.')
    with Session() as db:
        current = db.get(User, user.id)
        if current.provider_subscription_id and current.subscription_status in ('created', 'authenticated', 'active', 'pending'):
            subscription_id = current.provider_subscription_id
        else:
            subscription_id = None
    if not subscription_id:
        created = await razorpay('POST', 'subscriptions', json={
            'plan_id': plan, 'total_count': 120, 'quantity': 1, 'customer_notify': False,
            'notes': {'skilllens_user_id': user.id}})
        subscription_id = created['id']
        with Session.begin() as db:
            current = db.get(User, user.id)
            current.provider_subscription_id = subscription_id
            current.subscription_status = 'created'
    return {'key': os.environ['RAZORPAY_KEY_ID'], 'subscription_id': subscription_id,
            'name': 'SkillLens Pro', 'email': user.email}


@router.post('/billing/cancel')
async def cancel_subscription(user: User = Depends(require_user)):
    if not user.provider_subscription_id:
        raise HTTPException(400, 'No subscription linked to this account.')
    # Request cancellation at cycle end; entitlements change via authenticated webhook.
    data = await razorpay('POST', f'subscriptions/{user.provider_subscription_id}/cancel',
                          json={'cancel_at_cycle_end': 1})
    return {'status': data.get('status'), 'cancel_at_cycle_end': data.get('cancel_at_cycle_end', True),
            'message': 'Cancellation requested. Your plan will update after Razorpay confirms it.'}


@router.post('/webhooks/razorpay')
async def razorpay_webhook(request: Request):
    secret = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')
    if not secret:
        raise HTTPException(503, 'Webhook is not configured.')
    payload = await request.body()
    if len(payload) > 100000:
        raise HTTPException(413, 'Webhook too large.')
    provided = request.headers.get('x-razorpay-signature', '')
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, provided):
        raise HTTPException(400, 'Invalid webhook signature.')
    try:
        event = json.loads(payload)
    except ValueError:
        raise HTTPException(400, 'Invalid JSON.')
    event_id = request.headers.get('x-razorpay-event-id', '')
    if not event_id or len(event_id) > 140:
        raise HTTPException(400, 'Missing event ID.')
    with Session() as db:
        if db.get(WebhookEvent, event_id):
            return {'ok': True, 'duplicate': True}
    if not str(event.get('event', '')).startswith('subscription.'):
        with Session.begin() as db:
            db.merge(WebhookEvent(id=event_id))
        return {'ok': True}
    payload_sub = event.get('payload', {}).get('subscription', {}).get('entity', {})
    sub_id = payload_sub.get('id', '')
    if not re.fullmatch(r'sub_[A-Za-z0-9]+', sub_id):
        raise HTTPException(400, 'Malformed subscription event.')
    # Query source-of-truth state: handles out-of-order webhook deliveries.
    current = await razorpay('GET', f'subscriptions/{sub_id}')
    status = current.get('status', '')
    with Session.begin() as db:
        if db.get(WebhookEvent, event_id):
            return {'ok': True, 'duplicate': True}
        user = db.scalar(select(User).where(User.provider_subscription_id == sub_id))
        if not user:
            # Webhook can race with creation response; verified subscription notes tie it to the creator.
            claimed = (current.get('notes') or {}).get('skilllens_user_id', '')
            proposed = db.get(User, claimed) if claimed else None
            if proposed and proposed.provider_subscription_id in (None, sub_id):
                proposed.provider_subscription_id = sub_id
                user = proposed
        if user:
            user.subscription_status = status
            user.tier = 'pro' if status == 'active' and current.get('plan_id') == os.getenv('RAZORPAY_PLAN_ID') else 'free'
        db.add(WebhookEvent(id=event_id))
    return {'ok': True}


class DeleteAccount(BaseModel):
    password: str


@router.post('/account/delete')
def delete_account(data: DeleteAccount, request: Request, response: Response, user: User = Depends(require_user)):
    try:
        ph.verify(user.password_hash, data.password)
    except (argon_error.VerifyMismatchError, argon_error.VerificationError):
        raise HTTPException(403, 'Password incorrect.')
    if user.provider_subscription_id and user.subscription_status not in (None, 'cancelled', 'completed', 'expired'):
        raise HTTPException(409, 'Cancel your subscription and wait for cancellation confirmation before deleting your account.')
    from .payments import CheckoutOrder
    with Session.begin() as db:
        db.execute(delete(CheckoutOrder).where(CheckoutOrder.user_id == user.id))
        for model in (SessionToken, OneTimeToken, Usage, SavedReport, Application, ResumeDraft):
            db.execute(delete(model).where(model.user_id == user.id))
        db.execute(delete(User).where(User.id == user.id))
    response.delete_cookie(COOKIE_NAME, path='/', secure=PROD, httponly=True, samesite='lax')
    return {'ok': True, 'message': 'Account and saved reports deleted.'}

# Career dashboard: encrypted job-application tracker and editable resume drafts.
# Account endpoints use the existing auth cookie and CSRF enforcement.
APPLICATION_STATUSES = {'saved', 'applied', 'assessment', 'interview', 'offer', 'rejected', 'withdrawn'}


class ApplicationData(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    status: str = Field(default='saved', max_length=20)
    location: str = Field(default='', max_length=120)
    url: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=4000)
    next_step: str = Field(default='', max_length=200)


def validate_application(data: ApplicationData) -> dict:
    obj = data.model_dump()
    for key in ('company', 'role'):
        obj[key] = obj[key].strip()
        if not obj[key]:
            raise HTTPException(422, f'{key} cannot be blank.')
    if data.status not in APPLICATION_STATUSES:
        raise HTTPException(422, 'Invalid application status.')
    if data.url:
        parsed = urlparse(data.url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(422, 'A valid public HTTP(S) job URL is required.')
    return obj


def unpack_application(item: Application) -> dict:
    try:
        payload = json.loads(cipher.decrypt(item.encrypted_data.encode()).decode())
    except (InvalidToken, ValueError):
        raise HTTPException(503, 'Encrypted application could not be read.')
    return {'id': item.id, 'created_at': item.created_at.isoformat() + 'Z',
            'updated_at': item.updated_at.isoformat() + 'Z', **payload}


@router.get('/applications')
def applications(user: User = Depends(require_user)):
    with Session() as db:
        entries = db.scalars(select(Application).where(Application.user_id == user.id)
                             .order_by(Application.updated_at.desc()).limit(501)).all()
        return [unpack_application(item) for item in entries]


@router.post('/applications', status_code=201)
def create_application(data: ApplicationData, user: User = Depends(require_user)):
    payload = validate_application(data)
    with Session.begin() as db:
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
        count = db.scalar(select(func.count()).select_from(Application).where(Application.user_id == user.id))
        if count >= (500 if user.tier == 'pro' else 25):
            raise HTTPException(402, 'Application tracker limit reached.')
        item = Application(id=secrets.token_hex(16), user_id=user.id,
                           encrypted_data=cipher.encrypt(json.dumps(payload).encode()).decode())
        db.add(item)
    return {'id': item.id, **payload}


@router.put('/applications/{application_id}')
def update_application(application_id: str, data: ApplicationData, user: User = Depends(require_user)):
    payload = validate_application(data)
    with Session.begin() as db:
        item = db.get(Application, application_id)
        if not item or item.user_id != user.id:
            raise HTTPException(404, 'Application not found.')
        item.encrypted_data = cipher.encrypt(json.dumps(payload).encode()).decode()
        item.updated_at = utcnow()
    return {'id': application_id, **payload}


@router.delete('/applications/{application_id}')
def delete_application(application_id: str, user: User = Depends(require_user)):
    with Session.begin() as db:
        result = db.execute(delete(Application).where(Application.id == application_id,
                                                      Application.user_id == user.id))
        if not result.rowcount:
            raise HTTPException(404, 'Application not found.')
    return {'ok': True}


class ResumeDraftBody(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=100, max_length=55000)
    fields: dict[str, str] = Field(default_factory=dict)


def encrypt_draft(data: ResumeDraftBody) -> str:
    allowed = {'fullName', 'jobTitle', 'email', 'phone', 'city', 'links',
               'summary', 'skills', 'experience', 'projects', 'education', 'certifications'}
    if any(k not in allowed or not isinstance(v, str) for k, v in data.fields.items()) or any(
            len(value) > 7500 for value in data.fields.values()):
        raise HTTPException(422, 'Invalid resume fields.')
    payload = json.dumps({'text': data.text, 'fields': data.fields}, ensure_ascii=False)
    return cipher.encrypt(payload.encode()).decode()


def unpack_draft(item: ResumeDraft, include_text: bool = False) -> dict:
    base = {'id': item.id, 'title': item.title, 'updated_at': item.updated_at.isoformat() + 'Z',
            'expires_at': item.expires_at.isoformat() + 'Z'}
    if include_text:
        try:
            decoded = cipher.decrypt(item.encrypted_text.encode()).decode()
            # Backward-compatible with plaintext-encrypted v2 builder drafts.
            try:
                structured = json.loads(decoded)
                if isinstance(structured, dict) and 'text' in structured and 'fields' in structured:
                    base['text'] = structured['text']
                    base['fields'] = structured['fields']
                else:
                    base['text'] = decoded
            except (ValueError, TypeError):
                base['text'] = decoded
        except InvalidToken:
            raise HTTPException(503, 'Encrypted draft could not be read.')
    return base


@router.get('/drafts')
def list_drafts(user: User = Depends(require_user)):
    with Session() as db:
        return [unpack_draft(x) for x in db.scalars(select(ResumeDraft).where(
            ResumeDraft.user_id == user.id, ResumeDraft.expires_at > utcnow())
            .order_by(ResumeDraft.updated_at.desc()).limit(100)).all()]


@router.post('/drafts', status_code=201)
def save_draft(data: ResumeDraftBody, user: User = Depends(require_user)):
    with Session.begin() as db:
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
        count = db.scalar(select(func.count()).select_from(ResumeDraft).where(
            ResumeDraft.user_id == user.id, ResumeDraft.expires_at > utcnow()))
        if count >= (50 if user.tier == 'pro' else 5):
            raise HTTPException(402, 'Saved draft limit reached. Delete an older draft.')
        item = ResumeDraft(id=secrets.token_hex(16), user_id=user.id, title=data.title.strip(),
                           encrypted_text=encrypt_draft(data),
                           expires_at=utcnow() + timedelta(days=90))
        db.add(item)
    return unpack_draft(item)


@router.get('/drafts/{draft_id}')
def get_draft(draft_id: str, user: User = Depends(require_user)):
    with Session() as db:
        item = db.get(ResumeDraft, draft_id)
        if not item or item.user_id != user.id or item.expires_at <= utcnow():
            raise HTTPException(404, 'Draft not found.')
        return unpack_draft(item, True)


@router.put('/drafts/{draft_id}')
def update_draft(draft_id: str, data: ResumeDraftBody, user: User = Depends(require_user)):
    with Session.begin() as db:
        item = db.get(ResumeDraft, draft_id)
        if not item or item.user_id != user.id or item.expires_at <= utcnow():
            raise HTTPException(404, 'Draft not found.')
        item.title = data.title.strip()
        item.encrypted_text = encrypt_draft(data)
        item.updated_at = utcnow()
        item.expires_at = utcnow() + timedelta(days=90)
    return unpack_draft(item)


@router.delete('/drafts/{draft_id}')
def delete_draft(draft_id: str, user: User = Depends(require_user)):
    with Session.begin() as db:
        result = db.execute(delete(ResumeDraft).where(ResumeDraft.id == draft_id,
                                                     ResumeDraft.user_id == user.id))
        if not result.rowcount:
            raise HTTPException(404, 'Draft not found.')
    return {'ok': True}


@router.get('/account/export')
def export_account(request: Request, user: User = Depends(require_user)):
    # Sensitive bulk export requires session CSRF even on a read operation.
    session_auth(request, check_csrf=True)
    throttle('export:' + user.id, 5, 3600)
    with Session() as db:
        apps = [unpack_application(x) for x in db.scalars(select(Application).where(
            Application.user_id == user.id)).all()]
        reports = []
        for item in db.scalars(select(SavedReport).where(SavedReport.user_id == user.id,
                                                        SavedReport.expires_at > utcnow())).all():
            try:
                content = json.loads(cipher.decrypt(item.encrypted_report.encode()).decode())
            except (InvalidToken, ValueError):
                raise HTTPException(503, 'Cannot export an encrypted report.')
            reports.append({'title': item.title, 'created_at': item.created_at.isoformat() + 'Z', 'report': content})
        drafts = [unpack_draft(x, True) for x in db.scalars(select(ResumeDraft).where(
            ResumeDraft.user_id == user.id, ResumeDraft.expires_at > utcnow())).all()]
    from fastapi.responses import JSONResponse
    return JSONResponse({'exported_at': utcnow().isoformat() + 'Z', 'email': user.email,
                         'applications': apps, 'reports': reports, 'resume_drafts': drafts},
                        headers={'Cache-Control': 'no-store', 'Content-Disposition':
                                 'attachment; filename="skilllens-my-data.json"'})
