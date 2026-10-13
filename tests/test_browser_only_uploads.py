"""Guarantee paid deployments never accept unscanned raw resumes by default."""
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from app import main

ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT/'examples/sample_resume.txt').read_text()
JD = (ROOT/'examples/sample_job_description.txt').read_text()

def test_server_file_uploads_disabled_for_hosted_mode(monkeypatch):
    monkeypatch.setattr(main, 'PROD', True)
    monkeypatch.delenv('SKILLLENS_BACKEND_UPLOADS_ENABLED', raising=False)
    with TestClient(app) as c:
        cred={'email':'secure-'+uuid4().hex+'@example.org','password':'SecureTestPassword12345'}
        assert c.post('/api/auth/register',json=cred).status_code==200
        login=c.post('/api/auth/login',json=cred)
        assert login.status_code==200, login.text
        csrf=login.json()['csrf']
        headers={'X-CSRF-Token':csrf}
        rejected=c.post('/api/analyze',data={'job_description':JD},
                        files={'resume_file':('resume.txt',RESUME.encode(),'text/plain')},
                        headers=headers)
        assert rejected.status_code==422
        assert 'Import PDF/DOCX in your browser' in rejected.json()['detail']
        allowed=c.post('/api/analyze',data={'job_description':JD,'resume_text':RESUME},
                       headers=headers)
        assert allowed.status_code==200

def test_explicit_upload_enable_still_requires_scanner(monkeypatch):
    monkeypatch.setattr(main,'PROD',True)
    monkeypatch.setenv('SKILLLENS_ENV','production')
    monkeypatch.setenv('SKILLLENS_BACKEND_UPLOADS_ENABLED','true')
    monkeypatch.delenv('SKILLLENS_CLAMAV_ADDR',raising=False)
    with TestClient(app) as c:
        creds={'email':'scanner-'+uuid4().hex+'@example.org','password':'SecureTestPassword12345'}
        assert c.post('/api/auth/register',json=creds).status_code==200
        login=c.post('/api/auth/login',json=creds)
        csrf=login.json()['csrf']
        blocked=c.post('/api/analyze',data={'job_description':JD},
                       files={'resume_file':('resume.txt',RESUME.encode(),'text/plain')},
                       headers={'x-csrf-token':csrf})
        assert blocked.status_code==503
        assert 'scanner' in blocked.json()['detail'].lower()
