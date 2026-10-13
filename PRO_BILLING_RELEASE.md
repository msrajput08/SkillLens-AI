# SkillLens Pro — Final launch gate

Current public website: **free beta**. The existing ₹1 Razorpay Standard Checkout is a separate **test-only, one-time** payment; it never buys Pro.

## Pro subscription product

- Name: SkillLens Pro
- Monthly recurring price: **₹199 INR**, taxes/fees disclosed as applicable
- Features: 200 analyses/month, 100 rewrites/month, up to 100 saved reports
- Term: 12 monthly billing cycles, with renewal/reauthorisation to be designed before expiry
- Cancellation: in-app cancellation requests at end of paid cycle, provider-confirmed status
- Verification: signed Razorpay webhooks + Razorpay API authoritative subscription status + a paid cycle with future end time; **never** upgrade from a browser callback alone

## Before enabling actual charges

1. Razorpay merchant must explicitly show **Live Payments Activated** and the **Subscriptions** product must be enabled. **KYC submitted** is not sufficient.
2. Create Razorpay **Live Mode** monthly plan with `period=monthly`, `interval=1`, `amount=19900`, `currency=INR`. Store its `plan_...` ID privately.
3. Create Razorpay **Live Mode** webhook `https://skilllens-beta.onrender.com/api/webhooks/razorpay`, subscribing to `subscription.activated`, `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed` and payment events as relevant. Generate a separate webhook signing secret. Ensure URL and valid signatures tested using sandbox prior to any real customers.
4. Complete actual operator details, verified support email, business/refund/cancellation policy, privacy policy, GST/tax treatment where applicable and any merchant-hosting/consumer disclosures. Review legally. Set `LEGAL_REVIEWED=yes` only when true.
5. Move off Render Free to supported reliable hosting with monitoring and incident response, and backup + restoration rehearsal for Neon data and encrypted `SKILLLENS_DATA_KEY`. Do not change that key for existing encrypted user records.
6. Remove/purge any credentials previously exposed through chat, tickets or commits (both test and Neon), then store new API keys in **Render Environment**, never GitHub.
7. Verify subscription authorisation, first paid cycle, missed and repeated webhooks, delayed activation, failed renewal, cancellation/end-of-cycle behavior, account deletion block, refunds/disputes, duplicate signup and payment reconciliation.
8. Change Render from `render_beta` only after production dependencies including ClamAV scanner support and legal environment requirements are met; simply toggling the flag is **not** safe on a Free instance. Do not bypass fail-closed application checks.

**Only then** set these secret/private Render variables:

```dotenv
SKILLLENS_ENV=production
SKILLLENS_LAUNCH_MODE=production
SKILLLENS_PRO_BILLING_ENABLED=true
SKILLLENS_PRO_PRICE_INR=199
RAZORPAY_KEY_ID=rzp_live_REPLACE
RAZORPAY_KEY_SECRET=LIVE_SECRET_FROM_DASHBOARD
RAZORPAY_PLAN_ID=plan_REPLACE
RAZORPAY_WEBHOOK_SECRET=SEPARATE_WEBHOOK_SECRET
```

When billing isn't fully configured, Pro stays labeled **Coming soon** and checkout is disabled. Never use `rzp_test_` for paid Pro. Test Mode Standard Checkout is controlled separately by `SKILLLENS_STANDARD_CHECKOUT_ENABLED`; switch that to `false` for the customer-facing paid launch.

## Check before claiming launch

Run GitHub CI, real Render deploy, browser test in mobile and desktop, account recovery and privacy flows, security review, webhook failure/replay tests, restoration drill, validated cancellation/refund notice and merchant eligibility. Passing unit tests alone does not establish production security.

## Diagnostics
- `GET /api/billing/config` shows non-secret enabled state (never secret credentials).
- `POST /api/billing/status` requires verified login and CSRF, reconciles provider status before showing Pro.
- `POST /api/billing/checkout` returns 503 until live commerce gate is explicitly open.
