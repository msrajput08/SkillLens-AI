"""v3 tests for account isolation, encrypted drafts, and tool pages."""
from uuid import uuid4
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.saas import Session, Application, ResumeDraft

ROOT=Path(__file__).resolve().parents[1]

def make_user(client):
    user={'email':f'user-{uuid4().hex}@example.org','password':'StrictPassword123456'}
    r=client.post('/api/auth/register',json=user)
    assert r.status_code==200, r.text
    r=client.post('/api/auth/login',json=user)
    assert r.status_code==200, r.text
    return r.json()['csrf']

def test_application_store_private_and_encrypted():
    with TestClient(app) as a, TestClient(app) as b:
        acsrf=make_user(a); bcsrf=make_user(b)
        content={'company':'Sensitive Company','role':'Backend Engineer','status':'applied',
                 'location':'Remote','url':'https://example.org/job/123',
                 'notes':'Private notes about a test interview','next_step':'Reply next week'}
        r=a.post('/api/applications',json=content,headers={'x-csrf-token':acsrf})
        assert r.status_code==201,r.text
        identifier=r.json()['id']
        with Session() as db:
            item=db.get(Application,identifier)
            assert 'Sensitive Company' not in item.encrypted_data
            assert 'Private notes' not in item.encrypted_data
        assert len(a.get('/api/applications').json())==1
        assert b.get('/api/applications').json()==[]
        assert b.put('/api/applications/'+identifier,json=content,headers={'x-csrf-token':bcsrf}).status_code==404
        assert b.delete('/api/applications/'+identifier,headers={'x-csrf-token':bcsrf}).status_code==404
        assert a.put('/api/applications/'+identifier,json={**content,'status':'interview'},headers={'x-csrf-token':acsrf}).status_code==200
        assert a.delete('/api/applications/'+identifier,headers={'x-csrf-token':acsrf}).status_code==200

def test_application_url_and_csrf_validation():
    with TestClient(app) as c:
        csrf=make_user(c)
        bad={'company':'A','role':'B','url':'javascript:alert(1)'}
        assert c.post('/api/applications',json=bad,headers={'x-csrf-token':csrf}).status_code==422
        assert c.post('/api/applications',json={**bad,'url':''}).status_code==403
        assert c.post('/api/applications',json={**bad,'url':''},headers={'x-csrf-token':csrf}).status_code==201

def test_draft_privacy_expiration_and_export():
    with TestClient(app) as a,TestClient(app) as b:
        csrf=make_user(a);other=make_user(b)
        data={'title':'Private Resume','text':'Alpha Unique Token '+('Verified project details '*12)}
        r=a.post('/api/drafts',json=data,headers={'x-csrf-token':csrf})
        assert r.status_code==201,r.text
        uid=r.json()['id']
        with Session() as db:
            assert 'Alpha Unique Token' not in db.get(ResumeDraft,uid).encrypted_text
        assert b.get('/api/drafts').json()==[]
        assert b.get('/api/drafts/'+uid).status_code==404
        assert a.get('/api/drafts/'+uid).json()['text']==data['text']
        assert a.get('/api/account/export').status_code==403
        exp=a.get('/api/account/export',headers={'x-csrf-token':csrf})
        assert exp.status_code==200,exp.text
        assert exp.json()['resume_drafts'][0]['text']==data['text']
        assert b.delete('/api/drafts/'+uid,headers={'x-csrf-token':other}).status_code==404
        assert a.delete('/api/drafts/'+uid,headers={'x-csrf-token':csrf}).status_code==200

def test_cover_letter_is_evidence_first():
    source='Java Spring Boot PostgreSQL and REST APIs projects. '*7
    job='Build Spring Boot Java services, REST APIs and deploy PostgreSQL based backend systems.'*2
    with TestClient(app) as c:
        csrf=make_user(c)
        result=c.post('/api/cover-letter',json={'full_name':'Alex Example','company':'Demo Co',
            'role':'Backend Developer','resume_text':source,'job_description':job},
            headers={'x-csrf-token':csrf})
        assert result.status_code==200,result.text
        content=result.json()
        assert 'Alex Example' in content['draft']
        assert 'Demo Co' in content['draft']
        assert content['external_ai_used'] is False

def test_tool_pages_and_local_parsers():
    with TestClient(app) as c:
        for url,title in [('/builder','Resume Builder'),('/applications','Application Tracker')]:
            r=c.get(url);assert r.status_code==200;assert title in r.text
    importer=(ROOT/'app/static/importer.js').read_text()
    assert "pdfjs.getDocument" in importer
    assert "mammoth.extractRawText" in importer
    assert "new TextDecoder" in importer
