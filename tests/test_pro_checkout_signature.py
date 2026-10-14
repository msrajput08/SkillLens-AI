"""Signed subscription Checkout callback and paid-cycle verification."""
import hashlib
import hmac
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app import saas
from tests.test_saas import signup


def test_sub_checkout_requires_genuine_signature_and_paid_cycle(monkeypatch):
    secret = 'local-fake-razorpay-merchant-secret'
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', secret)
    monkeypatch.setenv('RAZORPAY_PLAN_ID', 'plan_TEST123')
    subscription_id = 'sub_' + uuid4().hex
    payment_id = 'pay_' + uuid4().hex
    remote = {'id':subscription_id, 'plan_id':'plan_TEST123', 'status':'authenticated',
              'paid_count':0, 'current_end':None}

    async def provider(method, path, **kw):
        assert method == 'GET' and path == 'subscriptions/' + subscription_id
        return dict(remote)

    monkeypatch.setattr(saas, 'razorpay', provider)
    with TestClient(app) as client:
        credentials, csrf = signup(client)
        with saas.Session.begin() as db:
            user = db.scalar(select(saas.User).where(saas.User.email==credentials['email']))
            user.provider_subscription_id = subscription_id
            user.subscription_status = 'created'
        proof = {'razorpay_payment_id':payment_id, 'razorpay_subscription_id':subscription_id,
                 'razorpay_signature': '0'*64}
        endpoint = '/api/billing/confirm'
        h = {'X-CSRF-Token':csrf}
        forged = client.post(endpoint, json=proof, headers=h)
        assert forged.status_code == 400
        assert client.get('/api/usage').json()['tier'] == 'free'
        proof['razorpay_signature'] = hmac.new(secret.encode(),
            (payment_id+'|'+subscription_id).encode(), hashlib.sha256).hexdigest()
        missing_csrf = client.post(endpoint, json=proof)
        assert missing_csrf.status_code == 403
        received = client.post(endpoint, json=proof, headers=h)
        assert received.status_code == 200, received.text
        assert received.json()['verified'] is True
        assert received.json()['tier'] == 'free'
        assert client.get('/api/usage').json()['tier'] == 'free'
        remote.update(status='active', paid_count=1, current_end=4102444800)
        confirmed = client.post(endpoint, json=proof, headers=h)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()['tier'] == 'pro'
        assert client.get('/api/usage').json()['tier'] == 'pro'
        wrong_id = dict(proof, razorpay_subscription_id='sub_other123456')
        denied = client.post(endpoint, json=wrong_id, headers=h)
        assert denied.status_code == 400


def test_checkout_browser_submits_signed_proof():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / 'app/static/saas.js').read_text()
    assert "/api/billing/confirm" in js
    for field in ('razorpay_payment_id', 'razorpay_subscription_id', 'razorpay_signature'):
        assert field + ':result.' + field in js
