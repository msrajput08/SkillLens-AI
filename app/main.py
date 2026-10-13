"""SkillLens local-first API. All resume data remains in request memory unless user opts into an LLM."""
from pathlib import Path
import asyncio
import logging
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
from .saas import router as saas_router, init_db, require_user, charge, ensure_quota, PROD, SITE_URL
from .legal import router as legal_router
from .malware import scan_resume

ROOT = Path(__file__).resolve().parent
app = FastAPI(title='SkillLens — Resume Intelligence', version='3.0.0', docs_url=None if PROD else '/api/docs', redoc_url=None, on_startup=[init_db])
app.include_router(saas_router)
app.include_router(legal_router)
app.mount('/assets', StaticFiles(directory=ROOT / 'static'), name='assets')


@app.on_event('startup')
async def periodic_retention_startup():
    # Render Free sleeps when idle; init_db purges on every cold start. While
    # active, keep purging records daily so a busy instance also honors TTLs.
    if PROD:
        async def run_cleanup():
            from .cleanup import purge
            while True:
                await asyncio.sleep(24 * 60 * 60)
                try:
                    await asyncio.to_thread(purge)
                except Exception:
                    logging.getLogger('skilllens.cleanup').exception('Scheduled retention cleanup failed')
        app.state.cleanup_task = asyncio.create_task(run_cleanup())


@app.on_event('shutdown')
async def periodic_retention_shutdown():
    task = getattr(app.state, 'cleanup_task', None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass



@app.middleware('http')
async def security_headers(request, call_next):
    # Explicitly reject cross-origin state changes; webhook signature is checked separately.
    if request.url.path.startswith('/api/'):
        # Fast reject declared oversized requests to protect small beta instances.
        # Endpoint-level parsing and upload limits still apply (including for
        # transfer-encoded/chunked requests without Content-Length).
        size_header = request.headers.get('content-length')
        if size_header is not None:
            try:
                size = int(size_header)
            except ValueError:
                return JSONResponse(status_code=400, content={'detail': 'Invalid Content-Length.'})
            limit = 8 * 1024 * 1024 if request.url.path in ('/api/analyze', '/api/rewrite') else 256 * 1024
            if size < 0 or size > limit:
                return JSONResponse(status_code=413, content={'detail': 'Request exceeds allowed size.'})
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.url.path != '/api/webhooks/razorpay':
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != SITE_URL:
            return JSONResponse(status_code=403, content={'detail': 'Cross-origin request blocked.'})
        if request.headers.get('sec-fetch-site', '').lower() == 'cross-site':
            return JSONResponse(status_code=403, content={'detail': 'Cross-site request blocked.'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
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


@app.get('/builder')
def builder():
    return FileResponse(ROOT / 'static' / 'builder.html')


@app.get('/tracker')
@app.get('/applications')
def tracker():
    return FileResponse(ROOT / 'static' / 'tracker.html')


@app.get('/robots.txt')
def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('User-agent: *\nAllow: /\nDisallow: /api/\n')


@app.get('/api/health')
def health():
    return {'ok': True, 'version': '3.0.0'}


@app.get('/api/capabilities')
def capabilities():
    return {'embedding': model_status(), 'custom_model': custom_status(), 'llm': llm_config(),
            'safe_rewrite': True, 'docx_export': True, 'resumes_persisted': False}




async def get_resume(resume_text: str, resume_file: UploadFile | None) -> str:
    resume = resume_text
    if resume_file is not None and resume_file.filename:
        content = await resume_file.read(MAX_UPLOAD + 1)
        try:
            if len(content) > MAX_UPLOAD:
                raise HTTPException(422, 'Resume file must be 6 MB or smaller.')
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
    ensure_quota(user, 'analyze')
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
    ensure_quota(user, 'rewrite')
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



class CoverLetterInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    company: str = Field(min_length=2, max_length=160)
    role: str = Field(min_length=2, max_length=160)
    resume_text: str = Field(min_length=100, max_length=55000)
    job_description: str = Field(min_length=80, max_length=40000)


@app.post('/api/cover-letter')
def create_cover_letter(data: CoverLetterInput, user = Depends(require_user)):
    """Evidence-first local template; does not call an external AI service.

    Do not invent employment, quantified impact, education, or credentials.
    Job-description keywords only appear when independently in the resume.
    """
    import re
    def clean_label(value: str) -> str:
        return re.sub(r'\\s+', ' ', value).strip()

    name = clean_label(data.full_name)
    company = clean_label(data.company)
    role = clean_label(data.role)
    required, preferred = _requirement_groups(data.job_description)
    matched = [skill for skill in dict.fromkeys(required + preferred)
               if _evidence(data.resume_text, skill)]
    if matched:
        evidence = 'My resume references ' + ', '.join(matched[:5]) + (
            ', among other skills.' if len(matched) > 5 else '.')
        fit = ('These overlap with technologies mentioned in the job description. '
               'I would welcome a chance to discuss the relevant projects and evidence.')
    else:
        evidence = ('I am interested in learning more about the responsibilities '
                    'and explaining which parts of my background are most relevant.')
        fit = 'I would welcome an opportunity to discuss my experience in more detail.'
    draft = '\\n'.join([
        name,
        '',
        f'Dear {company} Hiring Team,',
        '',
        f'I am writing to express my interest in the {role} position at {company}.',
        '',
        evidence + ' ' + fit,
        '',
        'Thank you for considering my application. I would be happy to share '
        'additional examples and discuss how my background may support your team.',
        '',
        'Sincerely,',
        name,
    ])
    return {'draft': draft, 'external_ai_used': False,
            'matched_skills': matched[:5],
            'notice': 'Editable evidence-first template. Verify every statement before applying.'}


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
