"""Anonymous first-party metrics: privacy, isolation and operational safety."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.metrics import DailyMetric
from app.saas import Session, utcnow


def test_public_event_is_aggregate_only_and_rejects_extra_fields():
    with TestClient(app) as client:
        day = utcnow().date().isoformat()
        key = ('preview_completed', '/', 'none', 'analysis', 'direct')
        with Session() as db:
            row = db.get(DailyMetric, (day, *key))
            before = row.count if row else 0
        item = {'event':key[0], 'page':key[1], 'feature':key[3], 'channel':key[4]}
        assert client.post('/api/analytics/event', json=item).status_code == 204
        assert client.post('/api/analytics/event', json=item).status_code == 204
        with Session() as db:
            row = db.get(DailyMetric, (day, *key))
            assert row.count == before + 2
            # These rows contain only predeclared categories and a daily count.
            assert not hasattr(row, 'user_id')
            assert not hasattr(row, 'ip_address')
            assert not hasattr(row, 'email')
        assert client.post('/api/analytics/event', json={
            **item, 'resume_text': 'Private resume secret'
        }).status_code == 422
        assert client.post('/api/analytics/event',json={
            'event':'page_view', 'page':'/', 'channel':'https://bad.com/utm?email=secret'
        }).status_code == 422
        assert client.post('/api/analytics/event', json={
            'event':'page_view', 'page':'/?resume=private'
        }).status_code == 422
        assert client.post('/api/analytics/event', json={
            'event':'page_view', 'page':'/', 'source':'pricing'
        }).status_code == 422


def test_telemetry_cross_origin_requests_are_blocked():
    with TestClient(app) as client:
        r = client.post('/api/analytics/event',
                        json={'event':'page_view','page':'/'},
                        headers={'Origin':'https://attacker.example'})
        assert r.status_code == 403


def test_summary_is_accessible_only_to_configured_verified_owner(monkeypatch):
    monkeypatch.delenv('SKILLLENS_ANALYTICS_ADMIN_EMAIL', raising=False)
    with TestClient(app) as client:
        anon = client.get('/api/analytics/summary')
        assert anon.status_code == 401
        creds = {'email':f'metrics-{uuid4().hex}@example.org',
                 'password':'PrivacyFocusedPassword1468'}
        assert client.post('/api/auth/register',json=creds).status_code == 200
        assert client.post('/api/auth/login',json=creds).status_code == 200
        assert client.get('/api/analytics/summary').status_code == 404
        monkeypatch.setenv('SKILLLENS_ANALYTICS_ADMIN_EMAIL', creds['email'])
        summary = client.get('/api/analytics/summary?days=30')
        assert summary.status_code == 200
        data = summary.json()
        assert data['period_days'] == 30
        assert data['event_counts']['preview_completed'] >= 2
        assert 'unique users' in data['note']
        assert 'acquisition_channels' in data
        assert client.get('/api/analytics/summary?days=91').status_code == 422
        monkeypatch.setenv('SKILLLENS_ANALYTICS_ADMIN_EMAIL','another@example.org')
        assert client.get('/api/analytics/summary').status_code == 404


def test_analytics_script_auto_counts_without_google_sdk_or_consent_banner():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    analytics = (root/'app/static/analytics.js').read_text()
    assert "send('page_view')" in analytics
    assert "credentials: 'omit'" in analytics
    assert "analytics.consent.v1" in analytics  # previous declines are respected
    assert "globalPrivacyControl" in analytics
    assert "resume_text" not in analytics
    assert "gtag(" not in analytics
    assert 'utm_source' in analytics
    assert 'URLSearchParams' in analytics
    assert "googletagmanager" not in analytics
    assert "skilllens-analytics-consent" not in analytics
    privacy = (root/'app/legal.py').read_text()
    assert 'data-analytics-optout' in privacy
    assert 'Google Analytics 4' in privacy
    for name in ['index', 'builder', 'tracker', 'resume-job-match',
                 'how-to-tailor-resume', 'resume-skills-gap']:
        html = (root/f'app/static/{name}.html').read_text()
        assert '/assets/analytics.js?v=20261117-aggregate1' in html
        assert '/assets/analytics.css' not in html
