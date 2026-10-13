"""Security, quota, isolation and subscription tests for commercial SaaS."""
import hashlib
import hmac
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.saas import Session, User, init_db, charge, usage_info
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT/'examples/sample_resume.txt').read_text()
JD = (ROOT/'examples/sample_job_description.txt').read_text()


def signup(client):
    credentials = {'email': f'security-{uuid4().hex}@example.com', 'password': 'ProperPassword4578'}
    assert client.post('/api/auth/register', json=credentials).status_code == 200
    logged = client.post('/api/auth/login', json=credentials)
    assert logged.status_code == 200, logged.text
    return credentials, logged.json()['csrf']


def test_anonymous_denied_and_registration():
    init_db()
    with TestClient(app) as client:
        no_auth=client.post('/api/analyze',data={'resume_text':RESUME,'job_description':JD})
        assert no_auth.status_code == 401
        data,csrf=signup(client)
        assert client.get('/api/auth/me').json()['user']['email']==data['email']
        # GET /me rotates csrf to reduce stale session token reuse.
        csrf=client.get('/api/auth/me').json()['csrf']
        forbidden=client.post('/api/analyze',data={'resume_text':RESUME,'job_description':JD})
        assert forbidden.status_code == 403
        yes=client.post('/api/analyze', data={'resume_text':RESUME,'job_description':JD},headers={'X-CSRF-Token':csrf})
        assert yes.status_code == 200, yes.text
        assert yes.json()['score']>=0
        assert client.post('/api/auth/logout', headers={'X-CSRF-Token':csrf}).status_code == 200
        assert client.get('/api/auth/me').status_code == 401


def test_saved_report_isolation_and_deletion():
    with TestClient(app) as a, TestClient(app) as b:
        _, ca = signup(a); _, cb = signup(b)
        report={'score':23,'role':'Demo role','evidence':[{'skill':'SQL','evidence':'secret example'}]}
        res=a.post('/api/reports',json={'title':'A private report','report':report},headers={'X-CSRF-Token':ca})
        assert res.status_code == 200,res.text
        report_id=res.json()['id']
        assert b.get('/api/reports/'+report_id).status_code == 404
        assert b.delete('/api/reports/'+report_id,headers={'X-CSRF-Token':cb}).status_code == 404
        assert a.get('/api/reports/'+report_id).json()==report
        assert a.delete('/api/reports/'+report_id,headers={'X-CSRF-Token':ca}).status_code == 200
        assert a.get('/api/reports/'+report_id).status_code == 404


def test_free_quotas_and_no_unearned_upgrade():
    with TestClient(app) as client:
        creds, csrf = signup(client)
        for index in range(5):
            res=client.post('/api/analyze',data={'resume_text':RESUME,'job_description':JD},headers={'X-CSRF-Token':csrf})
            assert res.status_code==200, (index,res.text)
        over=client.post('/api/analyze',data={'resume_text':RESUME,'job_description':JD},headers={'X-CSRF-Token':csrf})
        assert over.status_code==402,over.text
        assert client.get('/api/usage').json()['features']['analyze']['used']==5
        # Client cannot set plan or usage via public API.
        bad=client.post('/api/auth/login',json={**creds,'tier':'pro'})
        assert bad.json()['user']['tier']=='free'


def test_password_reset_invalid_does_not_change_account():
    with TestClient(app) as client:
        creds,csrf=signup(client)
        r=client.post('/api/auth/reset-password',json={'token':'x'*60,'new_password':'ChangedPassword23'})
        assert r.status_code==400
        assert client.post('/api/auth/login',json=creds).status_code==200


def test_rate_limiter_rejects_repeat_credentials():
    with TestClient(app) as client:
        email=f'bad-{uuid4().hex}@example.com'
        for i in range(10):
            assert client.post('/api/auth/login',json={'email':email,'password':'fakepassword1234'}).status_code == 401
        assert client.post('/api/auth/login',json={'email':email,'password':'fakepassword1234'}).status_code == 429


def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET','local-test-webhook-secret')
    with TestClient(app) as client:
        body={'event':'subscription.activated', 'payload':{'subscription':{'entity':{'id':'sub_fake'}}}}
        r=client.post('/api/webhooks/razorpay',json=body,headers={'x-razorpay-event-id':'evt_fake','x-razorpay-signature':'invalid'})
        assert r.status_code==400


def test_account_deletion_removes_own_saved_reports():
    with TestClient(app) as client:
        credentials, csrf = signup(client)
        saved=client.post('/api/reports',json={'title':'My draft','report':{'hello':'world'}},headers={'X-CSRF-Token':csrf})
        assert saved.status_code==200
        deleted=client.post('/api/account/delete',json={'password':credentials['password']},headers={'X-CSRF-Token':csrf})
        assert deleted.status_code==200,deleted.text
        assert client.get('/api/auth/me').status_code==401
        assert client.post('/api/auth/login',json=credentials).status_code==401


def test_signed_webhook_updates_tier_idempotently_and_rechecks_provider(monkeypatch):
    import app.saas as saas
    secret='only-for-local-test'
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', secret)
    monkeypatch.setenv('RAZORPAY_PLAN_ID', 'plan_abc123')
    state={'status':'active'}
    sub_id='sub_'+uuid4().hex[:18]
    async def fake_api(method, path, **kwargs):
        assert method=='GET'
        assert path=='subscriptions/'+sub_id
        return {'id':sub_id,'status':state['status'],'plan_id':'plan_abc123'}
    monkeypatch.setattr(saas, 'razorpay', fake_api)
    with TestClient(app) as client:
        credentials, csrf=signup(client)
        with saas.Session.begin() as db:
            u=db.scalar(saas.select(User).where(User.email==credentials['email']))
            u.provider_subscription_id=sub_id
            u.subscription_status='created'
        payload=json.dumps({'event':'subscription.activated','payload':{'subscription':{'entity':{'id':sub_id}}}}).encode()
        signature=hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
        headers={'x-razorpay-event-id':'event_'+uuid4().hex,'x-razorpay-signature':signature,'content-type':'application/json'}
        resp=client.post('/api/webhooks/razorpay',content=payload,headers=headers)
        assert resp.status_code==200,resp.text
        assert client.get('/api/usage').json()['tier']=='pro'
        replay=client.post('/api/webhooks/razorpay',content=payload,headers=headers)
        assert replay.status_code==200 and replay.json()['duplicate']
        state['status']='cancelled'
        headers['x-razorpay-event-id']='event_'+uuid4().hex
        gone=client.post('/api/webhooks/razorpay',content=payload,headers=headers)
        assert gone.status_code==200
        assert client.get('/api/usage').json()['tier']=='free'


def test_cross_origin_mutation_blocked():
    with TestClient(app) as client:
        response=client.post('/api/auth/register', json={'email':'test-'+uuid4().hex+'@example.com','password':'PasswordLong123456'},
                              headers={'origin':'https://attacker.example'})
        assert response.status_code==403


def test_report_ciphertext_contains_no_cleartext():
    import app.saas as saas
    with TestClient(app) as client:
        credentials, csrf=signup(client)
        key='sensitive-private-data-'+uuid4().hex
        response=client.post('/api/reports',json={'title':'Security check','report':{'evidence':key}},headers={'X-CSRF-Token':csrf})
        assert response.status_code==200
        report_id=response.json()['id']
        with saas.Session() as db:
            saved=db.get(saas.SavedReport,report_id)
            assert key not in saved.encrypted_report
            assert key==client.get('/api/reports/'+report_id).json()['evidence']


def test_upload_scanner_fails_closed(monkeypatch):
    from app.malware import scan_resume
    from fastapi import HTTPException
    monkeypatch.setenv('SKILLLENS_ENV','production')
    monkeypatch.delenv('SKILLLENS_CLAMAV_ADDR', raising=False)
    with pytest.raises(HTTPException) as exc:
        scan_resume(b'%PDF-1.7 example bytes')
    assert exc.value.status_code==503


def test_razorpay_plan_price_mismatch_is_rejected(monkeypatch):
    import app.saas as saas
    monkeypatch.setenv('RAZORPAY_PLAN_ID', 'plan_example')
    monkeypatch.setenv('SKILLLENS_PRO_PRICE_INR', '399')
    async def fake_api(method,path,**kw):
        return {'item':{'amount':59900,'currency':'INR'},'period':'monthly','interval':1}
    monkeypatch.setattr(saas,'razorpay',fake_api)
    with TestClient(app) as client:
        _,csrf=signup(client)
        result=client.post('/api/billing/checkout',headers={'X-CSRF-Token':csrf})
        assert result.status_code==503
        assert 'do not match' in result.json()['detail']
