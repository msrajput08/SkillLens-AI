# SkillLens security posture / threat model

**Not a security certification.** The app handles resumes and job-description content, which may contain personally identifying information and career history. Public deployment should be reviewed by security and privacy professionals.

## Trust boundaries

- Browser input: resume uploads, text, JD and user-supplied JSON reports are untrusted. The server enforces maximum sizes, in-memory parsing, user ownership and quotas. Frontend text is inserted with `textContent`, not HTML rendering.
- Login: Argon2id password hash, 12-character minimum, one-time SHA-256 hashed tokens, expiring database sessions via HTTP-only cookies, SameSite=Lax, Secure in production; CSRF header + origin check for authenticated mutations.
- Database: PostgreSQL on private Docker network in production. Optional report JSON is Fernet-encrypted. Resumes are not intentionally persisted as original files. Database backups still contain emails, billing status, report ciphertext and encryption-related metadata: protect backups and Fernet key separately.
- Payment: secrets are never returned in JSON. Signed Razorpay webhook body is checked before parsing; webhook event IDs are deduplicated; server re-fetches authoritative subscription status, and plan ID must match configured merchant plan. Browser payment success does not grant entitlements.
- AI provider: local NLP runs inside server. External rewrite calls are opt-in and use imperfect redaction. Users must be warned of data transfers, and provider retention/policies must be assessed.
- Uploads: scanned using ClamAV INSTREAM in production (fail closed), then parsed with constrained length/pages. This is defense in depth, **not a guarantee** against parser vulnerabilities or compression bombs. Consider dedicated parsing worker sandbox with CPU/time/memory constraints for large-scale exposure.

## Remaining professional work before launch

Threat-model review, code audit, dependency/CVE scan, Docker vulnerability scan, dynamic penetration test, cloud firewall/WAF and DDoS controls, end-to-end billing/subscription reconciliations, data protection impact/retention review, key-management and backup drills, real email deliverability, audit/alert monitoring, error tracking with PII redaction, load testing, structured operational incident process, refund and dispute policy, legal review of all customer-facing notices.

## Sensitive implementation notes

- `SKILLLENS_DATA_KEY` is REQUIRED in production. Do not rotate without migration/decryption/re-encryption plan; a changed key makes saved reports inaccessible.
- `SKILLLENS_LLM_API_KEY`, Razorpay key secret and webhook secret must be kept on the server, never JS or Git. `RAZORPAY_KEY_ID` is intended to be public.
- Strong CSP blocks inline scripts and embeds except Razorpay checkout. Validate third-party iframe/connect domains in real hosted checkout before release.
- Do not expose `/api/docs` in production; disabled automatically. Private endpoints return cache-control no-store.
- Production email, database and malware scanner required at application startup.
- The experimental scikit-learn model uses `joblib` deserialization; administrator must only load trusted local model artifacts.
- Account closure is deliberately blocked while subscriptions are active or pending. Cancellation should be confirmed by the payment provider before account closure.
- Public billing functionality has been simulated with signed test webhooks but **not** validated with a real merchant gateway.
