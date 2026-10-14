"""Commercial Pro billing release gates and provider-verified entitlements."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import saas

def test_billing_disabled_by_default(monkeypatch):
    monkeypatch.delenv('SKILLLENS_PRO_BILLING_ENABLED', raising=False)
    monkeypatch.setattr(saas,'PROD',True)
    monkeypatch.setattr(saas,'NO_CARD_BETA',False)
    monkeypatch.setenv('RAZORPAY_KEY_ID','rzp_live_fake')
    monkeypatch.setenv('RAZORPAY_PLAN_ID','plan_fake')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET','fake')
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET','fake')
    monkeypatch.setenv('SKILLLENS_PRO_PRICE_INR','199')
    monkeypatch.setenv('LEGAL_REVIEWED','yes')
    assert saas.pro_billing_enabled() is False
    assert saas.billing_config()['enabled'] is False

@pytest.mark.parametrize('key,missing', [
    ('RAZORPAY_KEY_ID','rzp_test_mock'),
    ('RAZORPAY_KEY_SECRET',''),
    ('RAZORPAY_PLAN_ID',''),
    ('RAZORPAY_WEBHOOK_SECRET',''),
    ('SKILLLENS_PRO_PRICE_INR','399'),
    ('LEGAL_REVIEWED','no'),
])
def test_commercial_feature_gate_requires_complete_live_configuration(monkeypatch,key,missing):
    monkeypatch.setattr(saas,'PROD',True)
    monkeypatch.setattr(saas,'NO_CARD_BETA',False)
    settings = {'SKILLLENS_PRO_BILLING_ENABLED':'true','RAZORPAY_KEY_ID':'rzp_live_mock',
                'RAZORPAY_KEY_SECRET':'fake','RAZORPAY_PLAN_ID':'plan_test',
                'RAZORPAY_WEBHOOK_SECRET':'fake','SKILLLENS_PRO_PRICE_INR':'199',
                'LEGAL_REVIEWED':'yes'}
    settings[key]=missing
    for k,v in settings.items(): monkeypatch.setenv(k,v)
    assert not saas.pro_billing_enabled()
    assert saas.billing_config()['enabled'] is False

def test_no_pro_without_provider_paid_cycle(monkeypatch):
    monkeypatch.setenv('RAZORPAY_PLAN_ID','plan_example')
    assert not saas.verified_paid_subscription({'status':'active','plan_id':'plan_example'})
    assert not saas.verified_paid_subscription({'status':'active','plan_id':'plan_example','paid_count':0,'current_end':4102444800})
    assert not saas.verified_paid_subscription({'status':'active','plan_id':'plan_wrong','paid_count':1,'current_end':4102444800})
    assert not saas.verified_paid_subscription({'status':'pending','plan_id':'plan_example','paid_count':1,'current_end':4102444800})
    assert not saas.verified_paid_subscription({'status':'active','plan_id':'plan_example','paid_count':1,'current_end':10000000})
    assert saas.verified_paid_subscription({'status':'active','plan_id':'plan_example','paid_count':1,'current_end':4102444800})

def test_refresh_subscription_requires_post_and_csrf(monkeypatch):
    email = f'billing-{uuid4().hex}@example.org'
    with TestClient(app) as client:
        creds={'email':email,'password':'BillingTesting12345'}
        assert client.post('/api/auth/register',json=creds).status_code==200
        response=client.post('/api/auth/login',json=creds)
        assert response.status_code==200
        csrf=response.json()['csrf']
        assert client.get('/api/billing/status').status_code==405
        assert client.post('/api/billing/status').status_code==403
        ok=client.post('/api/billing/status',headers={'x-csrf-token':csrf})
        assert ok.status_code==200 and ok.json()['tier']=='free'
        assert 'No recurring subscription' in ok.json()['message']

def test_plan_display_does_not_show_test_checkout_as_paid_pro():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    js=(root/'app/static/saas.js').read_text()
    assert "if(b.enabled && b.price === '199' && b.recurring)" in js
    assert "el('upgradeButton').hidden=true" in js
    assert "await refreshAccount()" in js
    assert "/api/billing/confirm" in js
    assert "/api/billing/status',{method:'POST'}" in js
    assert "grants_pro" in (root/'app/static/index.html').read_text() or 'Test Mode' in (root/'app/static/index.html').read_text()
