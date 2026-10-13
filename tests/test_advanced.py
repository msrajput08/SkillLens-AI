from tests.helpers import auth_post
"""Integration, privacy, export, training and negative-path tests."""
from pathlib import Path
from io import BytesIO
from unittest.mock import AsyncMock, Mock
import json
import os

import pytest
from docx import Document
from fastapi.testclient import TestClient
from app.main import app
from app.rewriter import candidate_lines, safe_rewrite, validate_suggestion, redacted
from app.custom_model import assess, status, _load
from training.train import train

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT / 'examples/sample_resume.txt').read_text()
JD = (ROOT / 'examples/sample_job_description.txt').read_text()


def form(**overrides):
    return {'resume_text': RESUME, 'job_description': JD,
            'target_role': 'Junior Backend Engineer', **overrides}


def test_capabilities_never_disclose_server_keys(monkeypatch):
    monkeypatch.setenv('SKILLLENS_LLM_API_KEY', 'VERY_PRIVATE_TEST_KEY')
    cap = client.get('/api/capabilities')
    assert cap.status_code == 200
    assert 'VERY_PRIVATE_TEST_KEY' not in cap.text
    assert cap.json()['resumes_persisted'] is False


def test_safe_rewrite_preserves_all_original_lines():
    response = auth_post(client, '/api/rewrite', data=form(mode='safe'))
    assert response.status_code == 200, response.text
    rewrite = response.json()
    assert rewrite['mode'] == 'safe'
    assert rewrite['draft'] == RESUME.strip()
    assert all(s['source_evidence'] == s['original'] for s in rewrite['suggestions'])
    assert any(s['relevant_skills'] for s in rewrite['suggestions'])


def test_safe_rewrite_rejects_unknown_mode_and_short_jd():
    assert auth_post(client, '/api/rewrite', data=form(mode='transformer')).status_code == 422
    assert auth_post(client, '/api/rewrite', data=form(job_description='tiny')).status_code == 422


def test_export_docx_round_trip():
    response = auth_post(client, '/api/export/docx', json={'draft': RESUME})
    assert response.status_code == 200, response.text
    assert 'attachment' in response.headers['content-disposition']
    doc = Document(BytesIO(response.content))
    full = ' '.join(p.text for p in doc.paragraphs)
    assert 'Java' in full
    assert 'Alex' in full
    assert 'no-store' in response.headers['cache-control']


def test_rewriter_basic_fabrication_guards():
    src = 'Built Java Spring Boot APIs and tested database queries.'
    assert validate_suggestion(src, 'Built Java Spring Boot APIs and tested database queries.')[0]
    assert not validate_suggestion(src, 'Built Java Spring Boot APIs with 99% uptime.')[0]
    assert not validate_suggestion(src, 'Built Java Spring Boot and Kubernetes deployment pipelines.')[0]
    assert not validate_suggestion(src, '100% ATS')[0]
    assert 'test@example.com' not in redacted('Email test@example.com and phone +91 98765 43210')
    assert '98765' not in redacted('Email test@example.com and phone +91 98765 43210')


def test_embeddings_explicit_configuration_required(monkeypatch):
    monkeypatch.delenv('SKILLLENS_EMBED_MODEL', raising=False)
    response = auth_post(client, '/api/analyze', data=form(semantic_mode='embeddings'))
    assert response.status_code == 503
    assert 'configure' in response.json()['detail'].lower()


def test_mocked_embeddings_are_plugged_into_score(monkeypatch):
    import app.main as main
    def fake_embedding(resume, jd):
        return {'score': 0.85, 'matches': [{'requirement': 'Python automation work',
            'resume_evidence': 'Created Python scripts for validation', 'similarity': 0.93}], 'model': 'mock-only'}
    monkeypatch.setattr(main, 'retrieval', fake_embedding)
    response = auth_post(client, '/api/analyze', data=form(semantic_mode='embeddings'))
    assert response.status_code == 200
    obj = response.json()
    assert obj['semantic']['model'] == 'mock-only'
    assert any(x['label'] == 'Semantic evidence relevance' for x in obj['breakdown'])


def test_training_creates_artifact_and_predicts(tmp_path, monkeypatch):
    file = tmp_path / 'trained.joblib'
    meta = train(ROOT / 'training/demo_labeled_pairs.csv', file, 'synthetic_demo')
    assert file.exists() and file.with_suffix('.json').exists()
    assert meta['evaluation']['test_examples'] > 0
    assert meta['evaluation']['held_out_groups']
    monkeypatch.setenv('SKILLLENS_CUSTOM_MODEL', str(file))
    _load.cache_clear()
    assert status()['available']
    prediction = assess('Experience with Java Spring Boot services', 'Built Java Spring Boot APIs for web applications.')
    assert 0 <= prediction['confidence'] <= 1
    assert 'not' in prediction['caution'].lower()
    response = auth_post(client, '/api/analyze', data=form(use_custom_model='true'))
    assert response.status_code == 200, response.text
    assert response.json()['custom_evidence']
    bad = auth_post(client, '/api/model/assess', json={'requirement': 'a', 'evidence': 'b'})
    assert bad.status_code == 422


def test_llm_refuses_external_transfer_without_consent(monkeypatch):
    monkeypatch.setenv('SKILLLENS_LLM_PROVIDER', 'openai_compatible')
    monkeypatch.setenv('SKILLLENS_LLM_MODEL', 'test-llm')
    monkeypatch.setenv('SKILLLENS_LLM_API_KEY', 'local-test-key')
    response = auth_post(client, '/api/rewrite', data=form(mode='llm', consent_external_ai='false'))
    assert response.status_code == 422
    assert 'consent' in response.json()['detail'].lower()


def test_llm_rejects_fabrication_and_uses_only_evidence(monkeypatch):
    import app.rewriter as rewriter
    monkeypatch.setenv('SKILLLENS_LLM_PROVIDER', 'openai_compatible')
    monkeypatch.setenv('SKILLLENS_LLM_MODEL', 'fake-llm')
    monkeypatch.setenv('SKILLLENS_LLM_API_KEY', 'local-test-key')
    lines = candidate_lines(RESUME, JD)
    assert lines
    forged = {'suggestions': [{'id': lines[0]['id'], 'suggested': 'Built Kubernetes microservices and improved performance by 300%.'}]}
    captured = []
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {'choices': [{'message': {'content': json.dumps(forged)}}]}
    class FakeClient:
        def __init__(self, *a, **kw):pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a):return None
        async def post(self, url, json, headers):
            captured.append((url, json, headers))
            return FakeResponse()
    monkeypatch.setattr(rewriter.httpx, 'AsyncClient', FakeClient)
    response = auth_post(client, '/api/rewrite', data=form(mode='llm', consent_external_ai='true'))
    assert response.status_code == 200, response.text
    edited = response.json()['suggestions'][0]
    assert edited['suggested'] == edited['original']
    assert edited['verification'].startswith('Rejected')
    assert captured[0][0].endswith('/chat/completions')
    assert 'alex@example.com' not in str(captured[0][1]).lower()
    assert 'local-test-key' not in response.text


def test_missing_custom_model_is_explicit(monkeypatch):
    monkeypatch.delenv('SKILLLENS_CUSTOM_MODEL', raising=False)
    assert auth_post(client, '/api/analyze', data=form(use_custom_model='true')).status_code == 503


def test_export_max_limit_validation():
    assert auth_post(client, '/api/export/docx', json={'draft': 'tiny'}).status_code == 422
    assert auth_post(client, '/api/export/docx', json={'draft': 'a'*55001}).status_code == 422
