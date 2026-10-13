# SkillLens — no-international-card public beta (Render Free + Neon + Brevo API)

This is **a deliberately restricted public-beta package** adapted from the commercial edition; it is NOT the complete monetized production release. It uses PostgreSQL, strong security headers, encrypted opt-in reports, user authentication and email verification. It **does not allow file uploads**, because the Render Free 512 MB instance cannot be assumed to host the required ClamAV service. Users can paste resume text; all upload requests are rejected in production until an antivirus scanner is configured. Paid checkout is disabled in this beta. Do not advertise a paid plan until verified payment/security tests have been completed.

## Accounts and URLs — no international card normally needed

- GitHub: https://github.com/ (private repository)
- Neon: https://console.neon.tech/ (Free PostgreSQL, currently 1 GB/project)
- Render: https://dashboard.render.com/ (Free Web Service; spins down after 15 minutes idle; ~1 minute wakeup)
- Brevo: https://www.brevo.com/ (verified sender + HTTPS API key; not SMTP, because free Render blocks outbound 25/465/587)

Providers may request additional anti-abuse verification; free tier quotas/pricing may change.

## Steps

1. Create a **private** GitHub repo. Extract ZIP and push the contents of `SkillLens_AI_Commercial_SaaS` as repo root, including `render.yaml`. NEVER commit secrets. Existing `.gitignore` excludes `.env.production`, `.env`, and dev key. Check `git status` before pushing.
2. Neon: Create Free database and copy the connection string. For SQLAlchemy psycopg3 use `postgresql+psycopg://...` instead of `postgresql://...` and **keep `sslmode=require`**. Use pooler URL only after testing migration and connection reliability. Handle special characters in credentials by retaining the provider's URL-encoded string.
3. Brevo: Authenticate a domain and **verify sender**. Create a transactional email API key and use `SMTP_FROM` as the verified sender address. Send a test email after deploy. API `POST https://api.brevo.com/v3/smtp/email` uses port 443.
4. Render: Dashboard → New → Blueprint → GitHub repo → select Free web service. All secrets must be set in Render Environment and never placed in `render.yaml` or GitHub.
5. Set Render environment variables:
   - `DATABASE_URL`: Neon PostgreSQL URL, `postgresql+psycopg://...` with TLS.
   - `SKILLLENS_SITE_URL`: exactly `https://YOUR_RENDER_SERVICE.onrender.com` (no trailing slash).
   - `SKILLLENS_DATA_KEY`: Fernet key, generated locally with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Back it up securely; do not rotate casually.
   - `BREVO_API_KEY`: secret from Brevo transactional API settings.
   - `SMTP_FROM`: your verified Brevo sender email.
   - `LEGAL_OPERATOR`: real registered individual/business operator.
   - `LEGAL_POSTAL_ADDRESS`: your real address for legal notices.
   - `LEGAL_CONTACT_EMAIL`: actual support email.
   - `LEGAL_REVIEWED=yes` **only after replacing starter privacy/terms pages and having policies genuinely reviewed**. Do not set this flag simply to make the app start.
   - `SKILLLENS_ENV=production` and `SKILLLENS_LAUNCH_MODE=render_beta` are set in `render.yaml`.
6. Review `app/legal.py` and replace template terms/privacy/refund policies with true disclosures **before accepting real personal data**. Commercial version also requires legal review and merchant approval.
7. On first deploy, Render Docker will install dependencies, run `alembic upgrade head` and serve on `$PORT`. Ensure `/api/health` and `/api/ready` return 200. Test account registration, a *real* email verification, paste-text analysis, safe rewrite and saved report in a second device. Confirm unauthorized accounts cannot see another account's reports.
8. Check the applicable Neon backup/export options and securely export database backups where supported. Store `SKILLLENS_DATA_KEY`. Neon free plan has quotas and the app can sleep; expired saved reports are inaccessible after 30 days and purged when the app next starts; avoid promising uptime for paying customers.

## Limits and monetization

No-card free beta gives an actual public URL for collecting feedback, not a high-availability commercial service. Free tier = 512 MB memory and 0.1 CPU on Render. Pretrained embedding weights, large local LLMs and ClamAV are **not** provisioned; use classic NLP and safe rewrite. `Pro` checkout hidden/disabled. Move to a paid instance or suitable secured infrastructure with malware scanning and complete acceptance testing before switching on resume file uploads and recurring billing. Do not circumvent card checks or deploy developer mode publicly.

For full commercial settings see `README.md` and `SECURITY.md`.
