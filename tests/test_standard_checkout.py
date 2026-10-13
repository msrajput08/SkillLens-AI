"""Offline Razorpay Standard Checkout contract tests. No network or real keys."""
import hashlib
import hmac
from uuid import uuid4
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app import payments
from app.saas import Session, User

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = 'rzp_test_fake_key_for_tests'
TEST_SECRET = 'offline-only-fake-test-secret'

def setup_test_checkout(monkeypatch):
    monkeypatch.setenv('SKILLLENS_STANDARD_CHECKOUT_ENABLED', 'true')
    monkeypatch.setenv('SKILLLENS_STANDARD_TEST_AMOUNT_PAISE', '100')
    monkeypatch.setenv('RAZORPAY_KEY_ID', TEST_KEY)
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', TEST_SECRET)

def login(client):
    email = f'checkout-{uuid4().hex}@example.org'
    creds = {'email': email, 'password': 'SecureTestPassword123'}
    assert client.post('/api/auth/register', json=creds).status_code == 200
    result = client.post('/api/auth/login', json=creds)
    assert result.status_code == 200, result.text
    return result.json()['csrf'], email

def gateway(monkeypatch, *, captured=True, payment_amount=100):
    order_id = 'order_' + uuid4().hex[:14]
    payment_id = 'pay_' + uuid4().hex[:14]
    calls = []
    async def fake_razorpay(method, path, **kwargs):
        calls.append((method,path))
        if method == 'POST' and path == 'orders':
            body = kwargs['json']
            assert body['amount'] == 100
            assert body['currency'] == 'INR'
            return {'id': order_id,'amount':body['amount'],
                    'currency':'INR','receipt':body['receipt'],'status':'created'}
        if method == 'GET' and path == 'payments/' + payment_id:
            return {'id':payment_id,'order_id':order_id,'currency':'INR',
                    'amount':payment_amount,'status':'captured' if captured else 'authorized'}
        raise AssertionError('Unexpected provider API request')
    monkeypatch.setattr(payments, 'razorpay', fake_razorpay)
    return order_id,payment_id,calls

def create(client, csrf):
    return client.post('/api/create-order', json={'amount':100,'currency':'INR'},headers={'x-csrf-token':csrf})

def signed(order_id,payment_id,secret=TEST_SECRET):
    signature=hmac.new(secret.encode(),f'{order_id}|{payment_id}'.encode(),hashlib.sha256).hexdigest()
    return {'razorpay_order_id':order_id,'razorpay_payment_id':payment_id,'razorpay_signature':signature}

def verify(client,csrf,payload):
    return client.post('/api/verify-payment',json=payload,headers={'x-csrf-token':csrf})

def test_checkout_is_off_until_enabled_and_never_uses_live_keys(monkeypatch):
    monkeypatch.setenv('SKILLLENS_STANDARD_CHECKOUT_ENABLED','false')
    with TestClient(app) as c:
        csrf,_=login(c)
        assert c.get('/api/standard-checkout/config').json()['enabled'] is False
        assert create(c,csrf).status_code==503
        monkeypatch.setenv('SKILLLENS_STANDARD_CHECKOUT_ENABLED','true')
        monkeypatch.setenv('RAZORPAY_KEY_ID','rzp_live_fake')
        monkeypatch.setenv('RAZORPAY_KEY_SECRET','fake')
        assert create(c,csrf).status_code==503

def test_order_requires_login_csrf_and_server_price(monkeypatch):
    setup_test_checkout(monkeypatch)
    _,_,calls=gateway(monkeypatch)
    with TestClient(app) as c:
        assert c.post('/api/create-order',json={'amount':100,'currency':'INR'}).status_code==401
        csrf,email=login(c)
        assert create(c,'invalid').status_code==403
        assert c.post('/api/create-order',json={'amount':50,'currency':'INR'},
                      headers={'x-csrf-token':csrf}).status_code==422
        assert c.post('/api/create-order',json={'amount':200,'currency':'INR'},
                      headers={'x-csrf-token':csrf}).status_code==400
        created=create(c,csrf)
        assert created.status_code==200,created.text
        data=created.json()
        assert data['amount']==100 and data['currency']=='INR'
        assert data['email']==email and data['grants_pro'] is False
        assert data['key_id']==TEST_KEY
        assert calls == [('POST','orders')]

def test_signature_validation_capture_replay_and_no_pro(monkeypatch):
    setup_test_checkout(monkeypatch)
    order_id,payment_id,calls=gateway(monkeypatch)
    with TestClient(app) as c:
        csrf,email=login(c)
        assert create(c,csrf).json()['order_id']==order_id
        assert verify(c,csrf,{}).status_code==400
        assert verify(c,csrf,signed(order_id,payment_id,'wrong-secret')).status_code==400
        assert calls==[('POST','orders')]
        result=verify(c,csrf,signed(order_id,payment_id))
        assert result.status_code==200,result.text
        assert result.json()['verified'] is True
        assert result.json()['grants_pro'] is False
        assert verify(c,csrf,signed(order_id,payment_id)).status_code==200
        assert verify(c,csrf,signed(order_id,payment_id,'wrong-secret')).status_code==400
        assert calls==[('POST','orders'),('GET','payments/'+payment_id)]
        with Session() as db:
            user=db.query(User).filter_by(email=email).one()
            assert user.tier=='free'

def test_uncaptured_or_incorrect_payment_cannot_succeed(monkeypatch):
    setup_test_checkout(monkeypatch)
    order_id,payment_id,_=gateway(monkeypatch,captured=False)
    with TestClient(app) as c:
        csrf,_=login(c)
        assert create(c,csrf).status_code==200
        assert verify(c,csrf,signed(order_id,payment_id)).status_code==409

    order_id,payment_id,_=gateway(monkeypatch,payment_amount=500)
    with TestClient(app) as c:
        csrf,_=login(c)
        assert create(c,csrf).status_code==200
        assert verify(c,csrf,signed(order_id,payment_id)).status_code==400

def test_order_cannot_be_verified_by_another_user(monkeypatch):
    setup_test_checkout(monkeypatch)
    order_id,payment_id,_=gateway(monkeypatch)
    with TestClient(app) as owner, TestClient(app) as stranger:
        owner_csrf,_=login(owner)
        stranger_csrf,_=login(stranger)
        assert create(owner,owner_csrf).status_code==200
        assert verify(stranger,stranger_csrf,signed(order_id,payment_id)).status_code==404

def test_provider_errors_do_not_mark_paid(monkeypatch):
    setup_test_checkout(monkeypatch)
    async def failure(method,path,**kwargs):
        raise HTTPException(502,'Payment provider request failed.')
    monkeypatch.setattr(payments,'razorpay',failure)
    with TestClient(app) as c:
        csrf,_=login(c)
        assert create(c,csrf).status_code==502

def test_checkout_ui_hooks_and_environment_hygiene():
    index=(ROOT/'app/static/index.html').read_text()
    javascript=(ROOT/'app/static/saas.js').read_text()
    ignore=(ROOT/'.gitignore').read_text()
    assert 'id="testCheckoutButton"' in index
    assert '/api/create-order' in javascript and '/api/verify-payment' in javascript
    assert 'payment.failed' in javascript and 'ondismiss' in javascript
    assert '.env' in ignore
