# SkillLens AI — Commercial SaaS Edition

**Deployment status:** Public no-card Render/Neon beta, not independently security-audited or payment-production certified. See [Production readiness gates](PRODUCTION_GATES.md) before accepting paid users.

**Status: application source + single-server deployment bundle.** This ZIP includes the integrated application, infrastructure configuration, tests and documentation. It is **not yet a live public website or a certified production release**. Real payment transactions, live SMTP delivery, DNS, TLS certificates, backups, legal documents, reliability and penetration testing require operator credentials and a real deployment environment. No API keys, merchant accounts, domains, or hosted model weights are included.

## Features actually implemented

| Area | Implemented |
|---|---|
| Job application intelligence | PDF/DOCX/TXT resume parsing, JD similarity, skills matched/missing, evidence, explainable job-match score, structured recommendations, interview practice |
| Resume rewriting | Source-preserving safe mode; optional local Ollama or external OpenAI-compatible model with opt-in and automated guards; DOCX/TXT exports |
| AI model training | Scikit-learn training/evaluation CLI and **synthetic demonstration model only**. Pretrained sentence embeddings are optional and downloadable separately |
| Accounts | Email/password account creation, Argon2 password hashing, email verification (SMTP in production), login, HttpOnly sessions, CSRF checks, password reset, logout, account deletion |
| Subscription billing | Razorpay Subscription creation and hosted Checkout JS, HMAC-SHA256 signature verification, event deduplication, server-side re-fetch of subscription state, current-plan entitlement checks, cycle-end cancellation request |
| User privacy | No raw resume file persistence, private encrypted **opt-in** report history, 30-day retention with purge worker, user-scoped database queries |
| Monetization | Free 5 analyses + 3 rewrites / month; Pro 200 analyses + 100 rewrites / month; saved reports: 5 / 100. Server-side transactional quota increments; calendar month UTC |
| Deployment | FastAPI, PostgreSQL, SQLAlchemy, Alembic baseline migration, Docker, Docker Compose, Caddy HTTPS, ClamAV INSTREAM scanner, retention worker |
| UI | Responsive landing page, analyzer, rewrite studio, member dialog, plans, saved-report list, account deletion, legal-template pages |
| Tests | Pytest integration/security/billing tests + isolated Chromium desktop/mobile rendering |

**Important model claims:** SkillLens scores are *NOT* employer ATS scores, job-hiring probabilities, or independently verified skill assessments. Synthetic-demo training performance is not real-world model accuracy. Any rewritten claims must be checked by the user.

## A. Try locally without payment credentials

Requires Python **3.11–3.13**. Run `start_windows.bat` on Windows or `bash start_linux_mac.sh` on Linux/macOS. Or:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open **http://localhost:8000**. Click **Sign in / Join free** → Create account. In **development only**, if SMTP is not configured, accounts are marked verified automatically. Sign in, use **Try with sample data**, analyze, inspect results, rewrite safely, save an encrypted report, reopen it from **My saved reports**, and delete it. The local SQLite database is `skilllens_dev.db` and the development-only encryption key is `.skilllens_dev_key`; back up both if you need persistent local reports. **Never use development mode on the public Internet.**

Optional local Docker:

```bash
docker compose up --build
```

This exposes **127.0.0.1:8000 only** and stores the development database and key in a Docker volume. No real checkout is enabled until merchant secrets are provided. On a public site without provider setup, users cannot purchase Pro.

## B. Real commercial deployment — required tasks

1. **Domain, server and business:** Buy a domain and a VPS with enough memory for Python, PostgreSQL and ClamAV (typically several GB RAM), set DNS `A/AAAA` records to server IP, open ports **80/443**, and configure server firewall/updates. Operator must supply real company/proprietor name, location/contact address, support process and legally reviewed terms/refund/privacy notices. Current `/privacy` and `/terms` are **starter templates, not finalized legal policies**.
2. **Merchant:** Onboard with **Razorpay**, enable Subscriptions, create a **monthly INR plan**, obtain plan ID, live API key ID/secret and webhook signing secret. Configure webhook to **`https://YOUR_DOMAIN/api/webhooks/razorpay`** for subscription events (activated, charged, paused, pending, halted, cancelled, completed, updated as supported). This site only upgrades from a server-retrieved active subscription matching your configured plan; **a browser success callback never grants Pro access**. Set the exact advertised monthly price in `.env.production`. The checkout endpoint validates the configured monthly INR plan price against Razorpay before creating subscriptions. Test actual flows in Razorpay TEST MODE first; never send test accounts live charges.
3. **Email:** Configure verified SMTP domain, SMTP host/port/username/password/from address, SPF/DKIM/DMARC and check inbox delivery for verification + password resets.
4. **AI:** The free analysis works with classical NLP by default. For stronger semantic matching, install `requirements-ai.txt` and configure `SKILLLENS_EMBED_MODEL`. For generative rewriting, set `SKILLLENS_LLM_PROVIDER=ollama` with an appropriately provisioned private Ollama server or `openai_compatible` and your server-only AI API credentials. Users must explicitly opt in to external calls. External provider redaction is **best effort**, not anonymous.
5. **Configure:** Copy `.env.production.example` to `.env.production` and replace **every** placeholder with real operator-controlled values. Generate a Fernet `SKILLLENS_DATA_KEY` once and store it safely; **losing this key makes historical reports unreadable**. Set `POSTGRES_PASSWORD` to a URL-safe random string because Compose embeds it in the connection URL. Do not commit `.env.production`.
6. **Run (Linux VPS with Docker Compose plugin):**

```bash
cp .env.production.example .env.production
# EDIT .env.production first; set PUBLIC_DOMAIN, site URL, legal and payment settings
# Python one-liner to generate data key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Caddy terminates HTTPS and gets TLS certificates for your DNS-ready domain. PostgreSQL is not published externally. The API migrates the schema before starting. The scanner container downloads ClamAV signatures during its initial startup, which may take time. Uploads **fail closed** if the production malware scanner cannot scan the file. Retention worker purges expired reports and credentials daily. Run `GET https://YOUR_DOMAIN/api/health` and `GET /api/ready`; use private test accounts.

7. **Mandatory go-live checks:** Verify paid test checkout, subscription active/cancelled/halted transition, webhook retry/duplicate/out-of-order delivery, billing portal/support journey, SMTP verification/reset, object-level isolation, malicious file rejection, load tests, disaster restore and real legal/tax obligations. Monitor errors and resources, review the threat model in `SECURITY.md`, set a paid plan price that covers inference + gateway + infrastructure costs. Have qualified security and legal reviewers check before handling real customers' private resumes.

### Razorpay specifics

The browser loads Razorpay Checkout from `https://checkout.razorpay.com/v1/checkout.js`, receiving only the publishable key ID and subscription ID. The secret stays server-side. API and webhooks use HMAC verification, re-query state from Razorpay, and confirm the merchant plan ID. Hosted checkout's complete CSP/payment journey needs testing against Razorpay's current live integration before launch. **No live payment was performed in this build.** India merchant eligibility/recurring payment availability must be confirmed with your account manager.

### Backups, rollback and incidents

Back up encrypted PostgreSQL dumps **off-server**, regularly test restoration, and retain the SkillLens Fernet encryption key separately from database backups. Use role-limited merchant keys and rotate secrets if compromised. Never store raw resume contents in logs or analytics. For DB backups with container credentials, e.g. `docker compose ... exec -T db pg_dump -U skilllens -d skilllens > private-backup.sql` (encrypt before off-site storage; this raw command produces an unencrypted dump). Stop publishing a broken deployment, restore prior Docker image + compatible schema/backup if needed. Alembic downgrade is deliberately blocked to prevent accidental destructive schema changes.

### Model accuracy and safety

See **`README_AI_ENGINE.md`** for the original ML pipeline, opt-in LLM adapters and candidate-evidence training. The included `models/demo_evidence.joblib` is trained on **fictional synthetic examples**. Do not represent its confidence as hiring probability, nor train on real people's resumes without lawful basis/consent and clear retention/privacy safeguards. Run human-labeled, group-separated evaluations, precision/recall tests and fairness review before using the custom classifier in customer-facing claims.

## C. QA, operations and known limitations

```bash
pip install -r requirements-dev.txt
python -m pytest -q
alembic upgrade head                 # initial local schema baseline
python -m app.cleanup                # remove expired local saved reports
```

- Current tests exercise API logic and mocked provider cases. **They do not prove real SMTP, ClamAV, DNS, TLS, Docker build or Razorpay transaction connectivity.** Isolated browser rendering checked static JS/layout, but direct localhost browser navigation was restricted by the execution environment.
- AI rewriting can hallucinate despite automated guards; users must review all edits. Embedding weights, LLM inference infrastructure, monitoring/alerting stack, real labeled model datasets, operator identity, legal copy, real billing credentials and production backups are **not shipped**.
- The SQLite mode is for local development only. Production requires PostgreSQL. SQLAlchemy initial metadata and baseline Alembic revision support new installs; review/add a versioned migration for future schema changes.
- Rate counters are shared through SQL, but a CDN/WAF with IP-level request filtering, application load tests and external vulnerability review are still needed. Ensure server and libraries are patched and browser privacy/cookies/payment UI work in production.
- Refund workflows, invoices/GST calculations, chargeback handling and support staff dashboard are external merchant/operator responsibilities in this edition, and **are not fully implemented**. Do not advertise compliance/certification or guaranteed hiring outcomes.
- For pricing, use the actual merchant recurring price; no amount has been invented in this source package.

**Production configuration checklist:** see `LAUNCH_CHECKLIST.md`. Legal review and live credentials are deployment blockers, not code placeholders to ignore.
