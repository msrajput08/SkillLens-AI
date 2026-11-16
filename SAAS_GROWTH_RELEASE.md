# SkillLens SaaS conversion foundation — release & operating checklist

> Branch-only change proposal. Merge and deploy only after review. **No production payment,
> entitlement, DNS, email-provider or infrastructure setting is changed by this PR.**

## Shipped in this change set

1. **Try before signup**: The homepage provides a useful, limited skill-match preview.
   `POST /api/preview` accepts only text, runs the existing explainable classic analyzer,
   returns one estimate and at most three matched/missing required skills. It returns no
   raw resume, evidence excerpts, full improvement plan, saved record or hiring prediction.
   Request fields are bounded to 12,000 characters each; the browser explains truncation.
   The persistent database rate limiter allows 20 preview calls per IP per 24-hour window.
   This is friction reduction, **not** abuse-proof. Retain WAF/IP throttling upstream and
   never call external paid AI models from the guest route.
2. **Sign up when value is visible**: A preview-to-account prompt opens registration without
   clearing the pasted text in the current tab. Email verification is still mandatory.
   The user should keep that tab open to retain their unsaved text. The full authenticated
   analyzer remains protected by session + CSRF and retains the 5-report free quota.
3. **Conversion at useful moments**: Full free reports show a contextual, non-blocking plan
   prompt. Quota errors show a route to the pricing section, including when checkout is
   temporarily unavailable. The app never grants Pro from a browser flag.
4. **Trustworthy pricing state**: The Pro plan displays the documented ₹199/month price
   and disabled checkout until `/api/billing/config` confirms recurring payments are
   enabled. Provider/API failures keep checkout disabled with a truthful explanation.
5. **Privacy-safe funnel analytics**: With user consent only, GA4 events can record
   analysis_started, preview_completed, signup_cta_clicked, signup_submitted,
   login_completed, analysis_completed, quota_exhausted, rewrite_completed,
   upgrade_cta_clicked, checkout_started, checkout_verified, and pro_activated.
   A fixed event and attribute allowlist prevents including email, resume, job description,
   job title or report contents. Consent refusal means these browser events are not recorded.
6. **Inference cost guardrails**: Rewrite bursts are capped at 12/hour per account via
   persistent throttling. Generative model completion sizes are capped at 1,200 tokens.
   The existing monthly quotas and pricing remain unchanged.

## QA before merging

- Run GitHub Actions on the PR: Python regression suite, browser JS syntax, Docker build.
- Fresh incognito window: paste resume + JD, click preview, verify no account is needed.
- Check result against the source data. Ensure preview shows only the limited result.
- Click Create free account, register, verify the actual email, sign in, and generate a
  detailed report. Confirm report quota and encrypted save/delete continue to work.
- Exhaust free quota with a test account, check upgrade link, and confirm checkout only
  activates when the server reports billing enabled.
- On narrow mobile screens (320px/375px), test all preview and pricing states.
- With analytics consent declined, verify no GA4 events fire; with consent accepted,
  inspect GA4 DebugView for the allowed event names and no sensitive user inputs.
- On the live **test merchant** configuration only, validate subscription checkout,
  callback, active paid period, webhook idempotency, cancellation and status refresh.
  Use an operator-controlled environment. Never charge customers just to validate this PR.
- Test cold starts, email verification delivery, backup restore, quota concurrency,
  error reporting and support contact procedures before scaling paid acquisition.

## Operating dashboard (do not infer these from repository code)

Track source-by-source:
`visitors → preview submissions → successful previews → registration submissions →
verified new users → full analyses → upgrade clicks → checkout attempts →
Razorpay-verified paid subscribers → monthly renewals`.

Also track support refunds, payment activation latency, cost per successful AI rewrite,
free-to-paid conversion, activation, churn, and **gross margin after gateway and hosting**.
Reconcile revenue with the Razorpay merchant dashboard, not GA4 checkout events.

## Not included, and still necessary to become a durable paid SaaS

- Real transaction + subscription reconciliation across multiple billing cycles, beyond
  existing repository tests and the operator's prior reported smoke test.
- Guaranteed uptime, domain, autoscaling, customer support SLA, monitoring and backup
  restoration drills. Render Free can sleep; paid users need a reliability plan.
- Replacing the current conservative safe rewriter with a more valuable feature.
  Do not call it AI-generated when no AI provider is configured.
- New one-time Job Sprint Pass, organization/college seats, or new price plans. These
  need a separate entitlement ledger, Razorpay live product configuration, refunds,
  and correctly reviewed terms before advertising/collecting payments.
- Proven acquisition/conversion metrics. Claims of new revenue require actual data.

## Rollback

No schema migration in this PR. Deploying the prior known-good commit reverts the UI
and guest route. Do not disable subscription webhooks or erase existing paid users.
