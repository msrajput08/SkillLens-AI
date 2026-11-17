"""Guest-to-member conversion regression tests (no external payment or model calls)."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT / "examples/sample_resume.txt").read_text()
JD = (ROOT / "examples/sample_job_description.txt").read_text()


def test_guest_preview_is_usable_without_signup_but_does_not_disclose_full_report():
    with TestClient(app) as client:
        response = client.post("/api/preview", json={
            "resume_text": RESUME,
            "job_description": JD,
            "target_role": "Java Backend Engineer",
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["role"] == "Java Backend Engineer"
        assert 0 <= data["alignment_estimate"] <= 100
        assert data["preview_only"] is True
        assert len(data["matched_skills"]) <= 3
        assert len(data["potential_gaps"]) <= 3
        assert "Java" in data["matched_skills"]
        assert "ATS" in data["disclaimer"]
        # The endpoint returns neither user resume text nor detailed evidence.
        assert "evidence" not in data
        assert "improvements" not in data
        assert "alex@example.com" not in response.text.lower()
        assert client.get("/api/auth/me").status_code == 401
        assert client.post("/api/analyze", data={
            "resume_text": RESUME, "job_description": JD
        }).status_code == 401


def test_guest_preview_rejects_short_and_excessively_large_payloads():
    with TestClient(app) as client:
        too_short = client.post("/api/preview", json={
            "resume_text": "short",
            "job_description": JD,
        })
        assert too_short.status_code == 422
        too_long = client.post("/api/preview", json={
            "resume_text": RESUME + ("extra " * 3000),
            "job_description": JD,
        })
        assert too_long.status_code == 422
        malformed = client.post("/api/preview", data={
            "resume_file": "not permitted", "job_description": JD,
        })
        assert malformed.status_code == 422


def test_preview_follows_same_origin_security_policy():
    with TestClient(app) as client:
        denied = client.post("/api/preview", json={
            "resume_text": RESUME,
            "job_description": JD,
        }, headers={"Origin": "https://attacker.example"})
        assert denied.status_code == 403


def test_frontend_has_preview_signup_and_safe_billing_fallback():
    html = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/app.js").read_text()
    auth = (ROOT / "app/static/saas.js").read_text()
    analytics = (ROOT / "app/static/analytics.js").read_text()
    assert 'id="guestPreviewState"' in html
    assert 'id="guestSignupButton"' in html
    assert 'id="quotaExplore"' in html
    assert "'/api/preview'" in script
    assert "window.openSignup" in auth
    assert 'id="upgradeButton"' in html
    assert 'disabled>Checking checkout' in html
    assert "Checkout currently unavailable" in auth
    assert "window.skilllensTrack" in analytics
    assert "credentials: 'omit'" in analytics
    assert "globalPrivacyControl" in analytics
    assert "skilllens-analytics-consent" not in analytics


def test_guest_preview_throttle_stops_inference(monkeypatch):
    import app.main as main
    from fastapi import HTTPException

    def blocked(*args, **kwargs):
        raise HTTPException(429, "Preview request limit reached.")

    def forbidden_inference(*args, **kwargs):
        raise AssertionError("Rate-limited requests must never reach the analyzer.")

    monkeypatch.setattr(main, "throttle", blocked)
    monkeypatch.setattr(main, "analyze", forbidden_inference)
    with TestClient(app) as client:
        response = client.post("/api/preview", json={
            "resume_text": RESUME,
            "job_description": JD,
        })
        assert response.status_code == 429
