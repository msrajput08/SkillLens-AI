"""Security regression tests for the no-card beta."""
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app import saas


def make_login(client):
    user = {'email': f'hardening-{uuid4().hex}@example.org', 'password': 'LongPass123456789'}
    assert client.post('/api/auth/register', json=user).status_code == 200
    return client.post('/api/auth/login', json=user).json()['csrf']


def test_unknown_login_not_hashing_again():
    with TestClient(app) as c, patch.object(saas, 'ph') as ph:
        response = c.post('/api/auth/login', json={'email': f'absent-{uuid4().hex}@example.org', 'password': 'Pass123456789'})
        assert response.status_code == 401
        ph.hash.assert_not_called()
        ph.verify.assert_called_once()


def test_quota_precheck_skips_inference():
    root = Path(__file__).resolve().parents[1]
    jd = (root/'examples/sample_job_description.txt').read_text()
    resume = (root/'examples/sample_resume.txt').read_text()
    with TestClient(app) as c:
        csrf = make_login(c)
        for _ in range(5):
            assert c.post('/api/analyze',data={'job_description':jd,'resume_text':resume},headers={'x-csrf-token':csrf}).status_code == 200
        with patch('app.main.analyze',side_effect=AssertionError('must not run')):
            assert c.post('/api/analyze',data={'job_description':jd,'resume_text':resume},headers={'x-csrf-token':csrf}).status_code == 402


def test_request_limits_and_cross_site_protection():
    with TestClient(app) as c:
        csrf = make_login(c)
        assert c.post('/api/auth/logout',content=b'x'*(300*1024),headers={'x-csrf-token':csrf}).status_code == 413
        assert c.post('/api/auth/logout',headers={'x-csrf-token':csrf,'sec-fetch-site':'cross-site'}).status_code == 403
        assert c.get('/api/health').headers['Cross-Origin-Resource-Policy'] == 'same-origin'


def test_beta_terms(monkeypatch):
    monkeypatch.setenv('SKILLLENS_LAUNCH_MODE','render_beta')
    with TestClient(app) as c:
        assert 'Paid checkout and Pro subscriptions are disabled' in c.get('/terms').text


def test_email_provider_error_not_leaking_credentials(monkeypatch,caplog):
    monkeypatch.setenv('BREVO_API_KEY','private-api-key')
    monkeypatch.setenv('SMTP_FROM','test@example.org')
    req = httpx.Request('POST','https://api.brevo.com/v3/smtp/email')
    resp = httpx.Response(403,request=req,text='sensitive response data')
    with patch.object(saas.httpx,'post',return_value=resp):
        from fastapi import HTTPException
        try:
            saas.send_email('recipient@example.org','Test','Private')
        except HTTPException as e:
            assert e.status_code == 503
    assert 'HTTP 403' in caplog.text
    assert 'recipient@example.org' not in caplog.text
    assert 'sensitive response data' not in caplog.text


def test_client_txt_import():
    root=Path(__file__).resolve().parents[1]
    assert 'id="importTextFile"' in (root/'app/static/index.html').read_text()
    assert "new TextDecoder('utf-8', {fatal: true})" in (root/'app/static/app.js').read_text()
