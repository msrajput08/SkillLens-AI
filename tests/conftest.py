"""Isolate rate-window state across independent tests and repeated local runs."""
import pytest
from sqlalchemy import delete
from app.saas import Session, RateWindow, init_db

@pytest.fixture(autouse=True)
def fresh_test_rate_window():
    init_db()
    with Session.begin() as db:
        db.execute(delete(RateWindow))
