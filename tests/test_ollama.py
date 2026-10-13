from tests.helpers import auth_post
from fastapi.testclient import TestClient
from pathlib import Path
import json
from app.main import app
from app.rewriter import candidate_lines

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
RESUME=(ROOT/'examples/sample_resume.txt').read_text()
JD=(ROOT/'examples/sample_job_description.txt').read_text()


def test_opt_in_ollama_rewrite_with_mocked_local_model(monkeypatch):
    import app.rewriter as rw
    monkeypatch.setenv('SKILLLENS_LLM_PROVIDER', 'ollama')
    monkeypatch.setenv('SKILLLENS_LLM_MODEL', 'fictional-test-model')
    first = candidate_lines(RESUME, JD)[0]
    revised = first['original']
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'message': {'content': json.dumps({'suggestions': [{'id': first['id'], 'suggested': revised}]})}}
    class FakeClient:
        def __init__(self,*a,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def post(self, url, json, headers):
            assert '/api/chat' in url
            assert json['format'] == 'json'
            return Response()
    monkeypatch.setattr(rw.httpx, 'AsyncClient', FakeClient)
    resp=auth_post(client, '/api/rewrite', data={'resume_text':RESUME,'job_description':JD, 'mode':'llm', 'consent_external_ai':'false'})
    assert resp.status_code==200,resp.text
    assert resp.json()['suggestions'][0]['original']==revised
    assert resp.json()['mode']=='llm'
