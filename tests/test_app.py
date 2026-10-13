from tests.helpers import auth_post
from io import BytesIO
from pathlib import Path
from fastapi.testclient import TestClient
from docx import Document
from app.main import app
from app.analyzer import analyze

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT / 'examples/sample_resume.txt').read_text()
JD = (ROOT / 'examples/sample_job_description.txt').read_text()


def test_app_home_and_health():
    assert client.get('/').status_code == 200
    assert b'SkillLens' in client.get('/').content
    assert client.get('/api/health').json()['ok'] is True


def test_analysis_has_explainable_evidence_and_gaps():
    result = analyze(RESUME, JD, 'Java Backend Engineer')
    assert 0 <= result['score'] <= 100
    assert 'Java' in result['required']['matched']
    assert 'Spring Boot' in result['required']['matched']
    assert 'OAuth' in result['required']['not_found']
    assert 'AWS' in result['preferred']['not_found']
    assert 'React' in result['preferred']['matched']
    assert sum(x['weight'] for x in result['breakdown']) == 100
    assert any(x['skill'] == 'Java' for x in result['evidence'])
    assert 'not a hiring prediction' in result['summary']


def test_api_text_and_text_not_stored():
    response = auth_post(client, '/api/analyze', data={'resume_text': RESUME, 'job_description': JD, 'target_role': 'Java engineer'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['role'] == 'Java engineer'
    assert 0 < result['score'] <= 100
    assert 'alex@example.com' not in response.text.lower()


def test_api_txt_upload():
    response = auth_post(client, '/api/analyze', data={'job_description': JD}, files={'resume_file': ('cv.txt', RESUME.encode(), 'text/plain')})
    assert response.status_code == 200, response.text
    assert response.json()['required']['total'] >= 4


def test_api_docx_upload():
    doc = Document()
    for line in RESUME.splitlines():
        doc.add_paragraph(line)
    b = BytesIO()
    doc.save(b)
    response = auth_post(client, '/api/analyze', data={'job_description': JD}, files={'resume_file': ('cv.docx', b.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    assert response.status_code == 200, response.text
    assert response.json()['required']['total'] >= 4


def test_reject_short_or_unsupported():
    assert auth_post(client, '/api/analyze', data={'resume_text': RESUME, 'job_description': 'short'}).status_code == 422
    response = auth_post(client, '/api/analyze', data={'job_description': JD}, files={'resume_file': ('cv.exe', RESUME.encode(), 'application/octet-stream')})
    assert response.status_code == 422
    assert 'Supported formats' in response.json()['detail']


def test_skills_no_java_javascript_collision():
    r = analyze('Jane Doe jane@sample.org\nEducation\nBS Engineering\nTechnical Skills\nJavaScript React HTML CSS\nProjects\nDeveloped frontend features and responsive web apps. ' + 'More description. '*10, JD)
    assert 'Java' in r['required']['not_found']
    assert 'React' in r['preferred']['matched']


def test_jd_no_dictionary_matches():
    resume = RESUME
    jd = ('Applicant will support the office with on-site logistics, coordinate daily vendor shipments, '
          'perform periodic stock checks, and handle telephone enquiries during opening hours. '
          'Excellent reliability and attention to operational details are expected for this position.')
    data = analyze(resume, jd)
    assert sum(b['weight'] for b in data['breakdown']) == 100
    assert data['required']['total'] == 0
    assert 'No skills' in data['notes']


def test_pdf_upload_end_to_end():
    from reportlab.pdfgen.canvas import Canvas
    buffer = BytesIO()
    pdf = Canvas(buffer)
    y = 780
    for line in RESUME.splitlines():
        pdf.drawString(40, y, line[:110])
        y -= 18
    pdf.save()
    response = auth_post(client, '/api/analyze', data={'job_description': JD},
        files={'resume_file': ('cv.pdf', buffer.getvalue(), 'application/pdf')})
    assert response.status_code == 200, response.text
    assert 'Java' in response.json()['required']['matched']


def test_oversized_file_is_rejected():
    response = auth_post(client, '/api/analyze', data={'job_description': JD},
        files={'resume_file': ('cv.txt', b'x' * (6 * 1024 * 1024 + 1), 'text/plain')})
    assert response.status_code == 422
    assert '6 MB' in response.json()['detail']
