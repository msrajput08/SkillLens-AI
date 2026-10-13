"""Authenticated legacy test adapter; security tests exercise raw endpoints separately."""
from uuid import uuid4
from app.saas import init_db
_auth = {}

def auth_post(client, url, **kwargs):
    if id(client) not in _auth:
        init_db()
        email = 'integration-' + uuid4().hex + '@example.com'
        body = {'email': email, 'password': 'CorrectHorseBattery1234'}
        created = client.post('/api/auth/register', json=body)
        assert created.status_code == 200, created.text
        login = client.post('/api/auth/login', json=body)
        assert login.status_code == 200, login.text
        _auth[id(client)] = login.json()['csrf']
        from app.saas import Session, User
        with Session.begin() as db:
            db.get(User, db.query(User).filter(User.email == email).first().id).tier = 'pro'
    headers = kwargs.pop('headers', {})
    return client.post(url, headers={**headers, 'X-CSRF-Token': _auth[id(client)]}, **kwargs)
