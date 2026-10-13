"""No-card deployment backend guarantees (no live external HTTP requests)."""
from unittest.mock import patch
from fastapi import HTTPException
from app import saas
from app.malware import scan_resume


def test_brevo_https_email_adapter(monkeypatch):
    monkeypatch.setenv('BREVO_API_KEY', 'unit-test-key')
    monkeypatch.setenv('SMTP_FROM', 'support@example.org')
    with patch.object(saas.httpx, 'post') as post:
        post.return_value.raise_for_status.return_value = None
        saas.send_email('test@example.org', 'Verify', 'Body')
        assert post.call_args.args[0] == 'https://api.brevo.com/v3/smtp/email'
        payload = post.call_args.kwargs['json']
        assert payload['to'] == [{'email': 'test@example.org'}]
        assert payload['textContent'] == 'Body'
        assert post.call_args.kwargs['headers']['api-key'] == 'unit-test-key'


def test_beta_uploads_fail_closed_without_scanner(monkeypatch):
    monkeypatch.setenv('SKILLLENS_ENV', 'production')
    monkeypatch.delenv('SKILLLENS_CLAMAV_ADDR', raising=False)
    try:
        scan_resume(b'untrusted upload bytes')
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError('Uploads should be blocked without a scanner')
