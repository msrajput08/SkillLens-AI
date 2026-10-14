"""No-charge Razorpay live-plan preflight and customer-facing subscription terms."""
import logging
import time
from fastapi.testclient import TestClient
from app import main, saas


def test_gateway_preflight_reads_plan_without_creating_subscriptions(monkeypatch, caplog):
    monkeypatch.setattr(main, 'PROD', True)
    settings = {
        'SKILLLENS_BILLING_PREFLIGHT':'true',
        'RAZORPAY_KEY_ID':'rzp_live_fake_testing_only',
        'RAZORPAY_KEY_SECRET':'dummy-private-testing-value',
        'RAZORPAY_WEBHOOK_SECRET':'different-fake-secret',
        'RAZORPAY_PLAN_ID':'plan_mock',
        'SKILLLENS_PRO_PRICE_INR':'199',
    }
    for key, value in settings.items(): monkeypatch.setenv(key, value)
    calls = []
    async def fake_razorpay(method, path, **kw):
        calls.append((method,path))
        return {'period':'monthly','interval':1,
                'item':{'amount':19900,'currency':'INR'}}
    monkeypatch.setattr(saas, 'razorpay', fake_razorpay)
    with caplog.at_level(logging.INFO,logger='skilllens.billing.preflight'):
        with TestClient(main.app) as client:
            assert client.get('/api/health').status_code==200
            time.sleep(.06)
    assert calls==[('GET','plans/plan_mock')]
    assert 'VERIFIED plan=INR199 monthly (read-only)' in caplog.text
    assert 'dummy-private-testing-value' not in caplog.text


def test_paid_beta_publishes_price_refund_cancel_and_free_hosting_caveats(monkeypatch):
    monkeypatch.setenv('SKILLLENS_LAUNCH_MODE','production')
    with TestClient(main.app) as client:
        terms=client.get('/terms')
        assert terms.status_code==200
        assert 'INR 199 per monthly billing cycle' in terms.text
        assert 'up to 12 cycles' in terms.text
        assert 'Cancellation and renewal' in terms.text
        assert 'Refund and payment disputes' in terms.text
        privacy=client.get('/privacy')
        assert 'free hosting tier' in privacy.text
        assert 'only extracted text' not in privacy.text


def test_billing_flag_not_reset_by_render_blueprint():
    from pathlib import Path
    yaml=(Path(__file__).resolve().parents[1]/'render.yaml').read_text()
    assert 'SKILLLENS_PRO_BILLING_ENABLED\n        sync: false' in yaml
