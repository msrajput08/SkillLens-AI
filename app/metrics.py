"""Anonymous aggregate product metrics — no cookies, identifiers, URLs or user text.

Never associate telemetry events with user accounts. No IP address, referrer,
user agent, resume/JD content or visitor ID is written to the metrics table.
Counts are events, not unique people; they can be affected by bots/ad blockers.
"""
import os
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from .saas import Base, Session, User, engine, require_user, utcnow

router = APIRouter()
MetricEvent = Literal[
    'page_view', 'analysis_started', 'preview_completed', 'analysis_completed',
    'signup_cta_clicked', 'signup_submitted', 'login_completed',
    'quota_exhausted', 'rewrite_completed', 'upgrade_cta_clicked',
    'checkout_started', 'checkout_verified', 'pro_activated'
]
MetricPage = Literal[
    '/', '/builder', '/applications', '/resume-job-match',
    '/guides/how-to-tailor-resume', '/guides/resume-skills-gap',
    '/privacy', '/terms', '/other'
]
MetricSource = Literal['none', 'preview', 'pricing', 'quota', 'account', 'report']
MetricFeature = Literal['none', 'analysis', 'rewrite']
MetricChannel = Literal[
    'direct', 'whatsapp', 'telegram', 'linkedin', 'x', 'email',
    'instagram', 'youtube', 'reddit', 'other'
]


class DailyMetric(Base):
    __tablename__ = 'daily_metrics'
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    event: Mapped[str] = mapped_column(String(40), primary_key=True)
    page: Mapped[str] = mapped_column(String(80), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    feature: Mapped[str] = mapped_column(String(20), primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MetricInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: MetricEvent
    page: MetricPage
    source: MetricSource = 'none'
    feature: MetricFeature = 'none'
    channel: MetricChannel = 'direct'


@router.post('/api/analytics/event', status_code=204, response_class=Response)
def record_event(data: MetricInput):
    """Record a single anonymous event in a daily aggregate counter.

    The browser posts with credentials:'omit'; no session is read, no
    identifying request headers are persisted and extra fields are rejected.
    """
    if data.event == 'page_view' and (data.source != 'none' or data.feature != 'none'):
        raise HTTPException(422, 'Page-view attributes are not supported.')
    values = dict(
        day=utcnow().date().isoformat(), event=data.event, page=data.page,
        source=data.source, feature=data.feature, channel=data.channel, count=1
    )
    if engine.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(DailyMetric).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=['day', 'event', 'page', 'source', 'feature', 'channel'],
        set_={'count': DailyMetric.count + 1}
    )
    with Session.begin() as db:
        db.execute(stmt)
    return Response(status_code=204)


@router.get('/api/analytics/summary')
def metric_summary(days: int = Query(default=30, ge=1, le=90),
                   user: User = Depends(require_user)):
    """Only an explicitly configured verified administrator may read counters."""
    admin = os.getenv('SKILLLENS_ANALYTICS_ADMIN_EMAIL', '').strip().lower()
    if not admin or user.email.lower() != admin:
        raise HTTPException(404, 'Not found.')
    first_day = (utcnow().date() - timedelta(days=days - 1)).isoformat()
    with Session() as db:
        rows = db.execute(
            select(DailyMetric.day, DailyMetric.event, DailyMetric.page,
                   DailyMetric.channel, func.sum(DailyMetric.count))
            .where(DailyMetric.day >= first_day)
            .group_by(DailyMetric.day, DailyMetric.event, DailyMetric.page, DailyMetric.channel)
            .order_by(DailyMetric.day)
        ).all()
    totals, page_views, channels, daily = {}, {}, {}, {}
    for day, event, page, channel, count in rows:
        count = int(count)
        totals[event] = totals.get(event, 0) + count
        if event == 'page_view':
            page_views[page] = page_views.get(page, 0) + count
            channels[channel] = channels.get(channel, 0) + count
        date_totals = daily.setdefault(day, {})
        date_totals[event] = date_totals.get(event, 0) + count
    return {
        'period_days': days, 'since_utc': first_day, 'event_counts': totals,
        'page_views': page_views, 'acquisition_channels': channels, 'daily_events': daily,
        'note': 'Aggregate event counts only. Not unique users, sessions, or verified paid revenue.'
    }
