# SkillLens v3 — Release handoff

## Branch and status
Reviewable source release candidate only. **Do not merge automatically or deploy onto the live Render service before the gates below pass**.

This branch adds:
- Browser-local PDF / DOCX / TXT text extraction. The original file is not uploaded; only extracted text goes to the existing analyzer API after explicit submission. Scanned PDFs without text require user-supplied OCR.
- New resume builder at `/builder` with TXT, print-to-PDF and authenticated DOCX export.
- Encrypted resume draft storage and retention.
- Evidence-first, non-generative cover letter at `/api/cover-letter`.
- Encrypted application tracker at `/applications` with CSV export.
- Private account data JSON export at `/api/account/export`.
- Alembic migration `0002_career_workspace`, a regression suite and launch documentation.

## Prior to deploying
1. **Back up Neon** using the provider’s supported mechanism and prove restore into an isolated database.
2. Back up the existing `SKILLLENS_DATA_KEY` securely and **do not regenerate** it while existing encrypted records are needed.
3. Rotate any previously disclosed credentials, then update Render and Neon before opening registrations to new users.
4. Use a staging Render service and staging Neon database with a dedicated staging encryption key. Do not send production secrets to staging.
5. Run `alembic upgrade head` in staging; verify the new tables and existing reports, user sessions and quotas.
6. Confirm staging succeeds on Render free tier including Node dependencies and PDF worker asset. If it doesn't fit memory, stop and optimize rather than bypassing scanning or lowering security.
7. Run `pytest -q`, browser imports and full registration-to-report acceptance tests; do **not** regard passing unit tests alone as production certification.
8. Review `/terms` and `/privacy` for actual operator details and third-party vendors. Do not mark `LEGAL_REVIEWED=yes` solely to bypass a startup guard.
9. Test failure scenarios, account isolation, sensitive-content handling and backup/restore before any paid beta.
10. Razorpay live payments remain disabled in `render_beta` mode. Enabling billing requires merchant onboarding, webhooks, refunds, failed payments, reconciliation, and reliable hosting.

## Deployment configuration
The existing `render.yaml` provides the no-card beta Blueprint and remains unchanged. Use current Render env variables and a PostgreSQL `postgresql+psycopg://` URL. Secrets must never enter source control. Review Dockerfile before build; parsers are pinned in `frontend/package.json`.

## Rollback
The `main` branch and current Render live deployment are unchanged by this PR. Rollback must include checking whether the schema change is additive; do not drop v3 tables or issue destructive downgrade. Restore from a separately tested backup if necessary.

## Disclaimers
Match score is **not** a recruiter ATS score. Resume outputs are templates and must be checked against source evidence. Browser parsing, encryption-at-rest, and quota enforcement do not imply that the service is independently security audited.
