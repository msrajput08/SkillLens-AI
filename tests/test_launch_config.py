"""Production launch display stays accurate and does not silently alter beta mode."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

def test_blueprint_allows_manual_launch_mode_without_override():
    content = (ROOT/'render.yaml').read_text()
    assert 'SKILLLENS_LAUNCH_MODE\n        sync: false' in content

def test_privacy_beta_vs_production(monkeypatch):
    with TestClient(app) as c:
        monkeypatch.setenv('SKILLLENS_LAUNCH_MODE', 'render_beta')
        beta = c.get('/privacy')
        assert beta.status_code == 200
        assert 'Razorpay sandbox checkout may be available' in beta.text
        monkeypatch.setenv('SKILLLENS_LAUNCH_MODE', 'production')
        paid = c.get('/privacy')
        assert paid.status_code == 200
        assert 'Paid subscriptions may be processed by Razorpay' in paid.text
        assert 'live subscription charges are not enabled' not in paid.text
