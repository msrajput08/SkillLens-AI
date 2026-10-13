# SkillLens AI — Resume Intelligence + Rewrite Studio

A **working local-first web application** that analyzes a resume against a job description, explains skill evidence, helps the user edit a tailored resume, and provides an **optional genuinely trained, experimentally evaluated custom classifier**. Responsive FastAPI + vanilla JS UI, with PDF/DOCX/TXT imports, MD/DOCX/TXT exports, and a Python model training pipeline.

**Status:** Local complete application for the features described here, not a hosted production SaaS. **No paid AI API credentials, local LLM weights or pretrained embedding weights are shipped.** The website works with classic NLP and extractive rewriting without accounts or keys. Optional stronger AI capabilities require separately installing/configuring models or access to a provider. Public commercial rollout needs authentication, billing, rate limiting, malware scanning, processing isolation, logging redaction, compliance and security review.

**Scores are NOT official ATS scores, employer screening decisions, interview predictions, or measures of merit.** Classifier probabilities are not hiring probabilities. Never use the experimental synthetic model to screen applicants.

## 1 — Run it now (no paid services)

Requires Python **3.11–3.13**. The easiest startup on Windows is to double-click **`start_windows.bat`**; on macOS/Linux run **`bash start_linux_mac.sh`**. These install the base dependencies in a local virtual environment (requires internet for first install) and start the web server.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000**. Press **Try with sample data** → **Analyze my resume** → **Rewrite studio** → choose **Safe** → **Generate tailored draft**. All controls work with no AI provider. The safe rewrite mode deliberately preserves factual wording rather than inventing achievements.

Alternative Docker run:

```bash
docker compose up --build
```

Open the same local URL. Docker binding is **loopback only** to avoid exposing an unauthenticated document service to the internet by accident.

## 2 — Features and model modes

| Feature | Works out of the box? | Model/technology |
|---|---|---|
| PDF/DOCX/TXT import, paste resume | Yes | pypdf, python-docx, guarded file parsing |
| JD and resume skill matching | Yes | lexical skill taxonomy + TF-IDF |
| Evidence, gaps, structure, score breakdown | Yes | explainable heuristic |
| Safe, truthful rewrite studio | Yes | source-preserving, ranked suggestion extraction |
| Editable draft, DOCX/TXT export | Yes | browser + python-docx |
| MD report export, PDF via print | Yes | browser |
| Semantic passage alignment | **Optional** | `sentence-transformers` pretrained embeddings |
| Model-assisted rewriting | **Optional** | Ollama local LLM or external OpenAI-compatible chat API |
| Custom supervised evidence classifier | **Optional** | trained sklearn pipeline; illustrative demo model included |
| Training and grouped holdout evaluation | Yes | Python CLI with user-supplied labeled CSV |

### 2a — Embeddings (opt-in)

```bash
pip install -r requirements-ai.txt
```

Set server environment variable:

```ini
SKILLLENS_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Use an existing local model directory instead if you want to avoid downloads. A Hugging Face model name downloads pretrained weights the first time the app explicitly requests embeddings. Initial downloads can be hundreds of MB and require internet; inference is local after caching. Check license of chosen model. Embeddings are for *similarity*, not competence verification; the UI displays retrieved snippets.

### 2b — Local Ollama rewriting (recommended privacy option)

Separately install [Ollama](https://ollama.com/), then download a compatible chat model (example):

```bash
ollama pull llama3.2:3b
ollama serve
```

Configure `.env` based on `.env.example`:

```ini
SKILLLENS_LLM_PROVIDER=ollama
SKILLLENS_LLM_MODEL=llama3.2:3b
SKILLLENS_OLLAMA_URL=http://127.0.0.1:11434
```

Then:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --env-file .env
```

`--env-file` requires `python-dotenv`, included in the normal dependencies. The server contacts the configured Ollama host. When running the app in Docker and Ollama on the host, use `http://host.docker.internal:11434` (configure Ollama listening/network permissions carefully). No LLM weights are included in this ZIP.

### 2c — External OpenAI-compatible API (explicit consent)

Use server-only credentials, never put secrets in JS, logs or source code:

```ini
SKILLLENS_LLM_PROVIDER=openai_compatible
SKILLLENS_LLM_MODEL=YOUR_SUPPORTED_CHAT_MODEL
SKILLLENS_LLM_BASE_URL=https://api.openai.com/v1
SKILLLENS_LLM_API_KEY=YOUR_PRIVATE_KEY
```

The UI requires an explicit consent checkbox before sending **best-effort redacted resume evidence excerpts** and **job-description excerpts** to an external provider. Redaction does not guarantee anonymity. Provider model IDs, JSON response handling and policies depend on the provider; an incompatible model may require adapter changes. User must verify suggested wording. The app intentionally **does not silently alter the source resume**.

## 3 — Train YOUR custom model

The project contains a **real sklearn classifier training pipeline**. It learns patterns in labeled `requirement ↔ resume evidence` pairs, evaluates on held-out **groups**, then fits a final model. It is *not* an LLM trained from scratch and *not* a general resume ATS predictor.

Training dataset schema (`training/demo_labeled_pairs.csv`):

```csv
requirement,evidence,label,group
"Requires Java backend service development","Developed Java REST APIs using Spring Boot",1,backend_family_1
"Requires Java backend service development","Created React frontend interfaces",0,backend_family_1
```

- `label=1` means the **specific sentence plausibly documents that requirement**; `0` means it does not. A term appearing in a skills list is not independently verified.
- `group` = resume, role or project family, assigned **before splitting** so near-duplicates across groups cannot leak into the holdout. For meaningful quality claims, include representative hard negatives and ensure all copies of a document share the same group.
- Collect real pairs only with informed consent, remove PII, have human subject-matter reviewers label them, audit class balance, compare against a lexical baseline, and evaluate on truly new role families. Avoid protected-attribute features and hiring/outcome labels.

Training CLI for the included fictional demo dataset:

```bash
python -m training.train --dataset training/demo_labeled_pairs.csv --output models/demo_evidence.joblib --dataset-kind synthetic_demo
```

Training on your verified, consented dataset:

```bash
python -m training.train --dataset path/to/human_pairs.csv --output models/my_evidence.joblib --dataset-kind human_labeled
```

Training generates two files: `.joblib` classifier and `.json` metadata with grouped holdout accuracy, precision, recall, F1, confusion matrix and held-out groups. **`joblib` artifacts execute pickle loading; never load files from unknown/untrusted origins.** Only enable files you trained and reviewed on your own server.

Activate **the included illustrative model (not production validated)** via:

```ini
SKILLLENS_CUSTOM_MODEL=models/demo_evidence.joblib
```

Restart server, enable **Evaluate evidence with custom-trained model** in UI. It shows exploratory evidence probabilities **separate from the resume alignment score**. The demo model's `1.0` held-out F1 on templated fictional pairs is *not evidence of real-world predictive performance*. The score does not change when enabling the custom classifier because it is not calibrated for applicant outcomes.

## 4 — Validation

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests cover original analyzer, PDF/DOCX/TXT upload, safe rewriting and claim guards, API validation, DOCX output, optional model fallback, grouped training, model loading, mocked embedding inference and mocked external LLM responses (without sending data). Browser smoke tests were run with isolated in-browser API fixtures and verified desktop/mobile layout and the rewrite UI. Actual service API was tested separately; public hosting and real remote LLM service were **not** tested end-to-end.

## 5 — API (at `/api/docs`)

- `POST /api/analyze`: multipart `job_description`, `resume_text` or `resume_file`, `target_role`, `semantic_mode=classic|embeddings`, `use_custom_model`
- `POST /api/rewrite`: same inputs + `mode=safe|llm`, `consent_external_ai` boolean
- `POST /api/export/docx`: JSON `{"draft":"..."}`
- `POST /api/model/assess`: JSON `{"requirement":"...","evidence":"..."}` (requires custom classifier configured)
- `GET /api/capabilities`, `GET /api/health`, `GET /api/docs`

## 6 — Privacy and important limitations

- By default, the server does not intentionally persist resumes, job descriptions, drafts, or history. **Uploaded multipart files can be temporarily spooled by Starlette**. Browser analysis and rewrite state is held only in the open tab.
- PDF ≤20 pages, uploaded file ≤6 MB; resume text ≤55K characters; JD ≤40K characters. No OCR for scanned/image-only PDFs.
- Parsing Office/PDF files can be risky; do not expose this local developer build publicly without isolated scanning/conversion workers, request/CPU/memory limits, antivirus, abuse protection, a reviewed privacy notice, auth, secret management, HTTPS and monitoring. Built-in header protections are defense-in-depth, not substitutes.
- Hosted LLM writing can introduce false claims despite automated safeguards. New technical skill/number guards only catch some errors; user approval is mandatory. Contact details redaction is best-effort, not de-identification.
- Real employers use different ATS products and recruiter workflows. Resume alignment here cannot establish skill proficiency or predict interview chances. Consider accessibility and fairness impacts when deploying.
- Demo examples and training pairs are fictional. No user resume is included in the shipped training examples.

## Architecture

```text
app/
  main.py             REST API, request validation, security headers
  analyzer.py         explainable lexical/skill analysis
  semantic.py         opt-in local sentence embeddings and passage retrieval
  custom_model.py     opt-in custom supervised classifier scoring
  model_features.py   overlap features supporting trained pipeline
  rewriter.py         source-linked safe/LLM copyedit suggestions and safeguards
  exports.py          DOCX export for reviewed draft
  parsing.py          PDF/DOCX/TXT bounded parsing
  taxonomy.py         curated skill aliases
  static/             responsive full web application
training/
  train.py            grouped evaluation + artifact creation
  demo_labeled_pairs.csv
models/
  demo_evidence.joblib / .json   fictional DEMO model and metrics
examples/             fictional sample resume and JD
tests/                API, training, security/privacy unit tests
Dockerfile / docker-compose.yml
.env.example
```

Build responsibly; improve the UI and scoring with **evaluated evidence**, not a made-up “99% ATS score.”
