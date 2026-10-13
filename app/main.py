"""SkillLens local-first API. All resume data remains in request memory unless user opts into an LLM."""
from pathlib import Path
from io import BytesIO
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer import analyze, _requirement_groups, _evidence
from .parsing import ResumeParseError, MAX_UPLOAD, extract_resume
from .semantic import retrieval, SemanticUnavailable, model_status
from .custom_model import assess, status as custom_status, CustomModelUnavailable
from .rewriter import ai_rewrite, safe_rewrite, RewriteError, llm_config
from .exports import draft_docx
from .saas import router as saas_router, init_db, require_user, charge, PROD, SITE_URL
from .legal import router as legal_router
from .malware import scan_resume

ROOT = Path(__file__).resolve().parent
app = FastAPI(title='SkillLens — Resume Intelligence', version='2.0.0', docs_url=None if PROD else '/api/docs', redoc_url=None, on_startup=[init_db])
app.include_router(saas_router)
app.include_router(legal_router)
app.mount('/assets', StaticFiles(directory=ROOT / 'static'), name='assets')


@app.middleware('http')
async def security_headers(request, call_next):
    # Explicitly reject cross-origin state changes; webhook signature is checked separately.
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.url.path != '/api/webhooks/razorpay':
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != SITE_URL:
            return JSONResponse(status_code=403, content={'detail': 'Cross-origin request blocked.'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self' https://checkout.razorpay.com; style-src 'self'; img-src 'self' data: https://*.razorpay.com; frame-src https://*.razorpay.com; "
        "connect-src 'self' https://*.razorpay.com; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    if PROD:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


@app.get('/')
def home():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/robots.txt')
def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('User-agent: *\nAllow: /\nDisallow: /api/\n')


@app.get('/api/health')
def health():
    return {'ok': True, 'version': '2.0.0'}


@app.get('/api/capabilities')
def capabilities():
    return {'embedding': model_status(), 'custom_model': custom_status(), 'llm': llm_config(),
            'safe_rewrite': True, 'docx_export': True, 'resumes_persisted': False}


async def get_resume(resume_text: str, resume_file: UploadFile | None) -> str:
    resume = resume_text
    if resume_file is not None and resume_file.filename:
        content = await resume_file.read(MAX_UPLOAD + 1)
        try:
            scan_resume(content)
            resume = extract_resume(resume_file.filename, content)
        except ResumeParseError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        finally:
            await resume_file.close()
    if len(resume.strip()) < 100:
        raise HTTPException(422, detail='Please upload a readable resume or paste at least 100 characters.')
    if len(resume) > 55000:
        raise HTTPException(422, detail='Resume text must be 55,000 characters or fewer.')
    return resume


def check_jd(jd: str, role: str):
    if len(jd.strip()) < 80:
        raise HTTPException(422, detail='Please provide at least 80 characters of the job description.')
    if len(jd) > 40000:
        raise HTTPException(422, detail='Job description must be 40,000 characters or fewer.')
    if len(role) > 120:
        raise HTTPException(422, detail='Role title is too long.')


@app.post('/api/analyze')
async def analyze_endpoint(
    job_description: str = Form(...), target_role: str = Form(''), resume_text: str = Form(''),
    resume_file: UploadFile | None = File(None), semantic_mode: str = Form('classic'),
    use_custom_model: bool = Form(False), user = Depends(require_user),
):
    check_jd(job_description, target_role)
    if semantic_mode not in ('classic', 'embeddings'):
        raise HTTPException(422, detail='semantic_mode must be classic or embeddings.')
    resume = await get_resume(resume_text, resume_file)
    semantic = None
    evidence = []
    if semantic_mode == 'embeddings':
        try:
            semantic = retrieval(resume, job_description)
        except SemanticUnavailable as exc:
            raise HTTPException(503, detail=str(exc)) from exc
    if use_custom_model:
        try:
            required, preferred = _requirement_groups(job_description)
            for skill in (required + preferred)[:12]:
                snippet = _evidence(resume, skill)
                if snippet:
                    result = assess(f'Experience with {skill}', snippet)
                    evidence.append({'skill': skill, 'source_evidence': snippet, **result})
        except CustomModelUnavailable as exc:
            raise HTTPException(503, detail=str(exc)) from exc
    result = analyze(resume, job_description, target_role, semantic=semantic, custom_evidence=evidence)
    charge(user, 'analyze')
    return result


@app.post('/api/rewrite')
async def rewrite_endpoint(
    job_description: str = Form(...), target_role: str = Form(''), resume_text: str = Form(''),
    resume_file: UploadFile | None = File(None), mode: str = Form('safe'),
    consent_external_ai: bool = Form(False), user = Depends(require_user),
):
    check_jd(job_description, target_role)
    if mode not in ('safe', 'llm'):
        raise HTTPException(422, detail='mode must be safe or llm.')
    resume = await get_resume(resume_text, resume_file)
    if mode == 'safe':
        result = safe_rewrite(resume, job_description, target_role)
    else:
        try:
            result = await ai_rewrite(resume, job_description, target_role, consent_external_ai)
        except RewriteError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
    charge(user, 'rewrite')
    return result


class ExportDraft(BaseModel):
    draft: str = Field(min_length=20, max_length=55000)


@app.post('/api/export/docx')
def export_docx(data: ExportDraft, user = Depends(require_user)):
    docx = draft_docx(data.draft)
    return StreamingResponse(BytesIO(docx), media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                             headers={'Content-Disposition': 'attachment; filename="skilllens-tailored-resume.docx"',
                                      'Cache-Control': 'no-store'})


class EvidencePair(BaseModel):
    requirement: str = Field(min_length=12, max_length=1500)
    evidence: str = Field(min_length=12, max_length=2000)


@app.post('/api/model/assess')
def model_assess(pair: EvidencePair, user = Depends(require_user)):
    try:
        return assess(pair.requirement, pair.evidence)
    except CustomModelUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc


@app.exception_handler(413)
async def over_limit(_, exc):
    return JSONResponse(status_code=413, content={'detail': 'Upload is too large.'})


@app.get('/api/ready')
def readiness():
    from sqlalchemy import text as sqltext
    from .saas import engine
    try:
        with engine.connect() as db:
            db.execute(sqltext('SELECT 1'))
    except Exception:
        raise HTTPException(503, 'Database not ready.')
    return {'ready': True}
