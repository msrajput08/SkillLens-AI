# SkillLens production-readiness gates

Current status: **limited public beta**, not security-audited or certified for paid production.

## Before a release
- Review code changes, ensure all tests and CI pass, and record a known-good rollback commit.
- Rotate previously exposed Neon DB credentials; never publish database URLs or API keys.
- Verify signup, verified email, login, forgotten-password, logout and account deletion.
- Test cross-user report isolation, quotas, invalid CSRF and expired sessions.
- Keep SKILLLENS_DATA_KEY securely backed up and unchanged without a tested key-rotation procedure.
- Check /api/ready, /api/health and recovery after Render sleeping; exercise restore from encrypted backups.
- Verify legal pages match actual Render, Neon and Brevo processing arrangements and retention; arrange independent legal review.

## Before enabling paid users
- Secure reliable hosting, backups, monitoring, alerts and incident response.
- Perform independent vulnerability review, concurrency/load/abuse tests, rate limiting and accessibility checks.
- Configure virus scanning before enabling backend file uploads. Do not bypass fail-closed scanner.
- Test Razorpay merchant sandbox renewals, webhooks (signed, repeated, late and out of order), refunds, chargebacks, reconciliation and cancellation. Obtain merchant/legal approval.
- Evaluate optional generative AI using consented test cases, verify it does not invent accomplishments, and limit costs.
- Never claim scores are official ATS predictions.

## Rollback
Redeploy the previous known-good Render commit if needed. Avoid irreversible database migrations without a pre-change verified backup.
