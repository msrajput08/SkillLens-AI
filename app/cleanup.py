"""Run periodically (e.g. once a day) for data retention and credential hygiene."""
from datetime import timedelta
from sqlalchemy import delete
from .saas import Session, SavedReport, SessionToken, OneTimeToken, RateWindow, WebhookEvent, utcnow


def purge():
    now = utcnow()
    removed = {}
    with Session.begin() as db:
        for model, predicate in [
            (SavedReport, SavedReport.expires_at <= now),
            (SessionToken, SessionToken.expires_at <= now),
            (OneTimeToken, OneTimeToken.expires_at <= now),
            (RateWindow, RateWindow.expires_at <= now - timedelta(days=1)),
            (WebhookEvent, WebhookEvent.processed_at <= now - timedelta(days=90)),
        ]:
            removed[model.__tablename__] = db.execute(delete(model).where(predicate)).rowcount
    return removed


if __name__ == '__main__':
    print('Retention cleanup counts:', purge())
