# Cookie-free aggregate analytics release

This release removes the **Allow analytics / Decline** modal. Page views and product-funnel
events are automatically counted with a first-party API. It **replaces GA4 client tracking**
rather than enabling Google cookies for everyone. Existing Google Analytics reporting will
no longer receive new page/event data from SkillLens after this deployment.

## Private reporting access (one Render environment variable)

Add **SKILLLENS_ANALYTICS_ADMIN_EMAIL** to the Render service environment and set
it to the **verified SkillLens login email** for the operator account. Example:

```
SKILLLENS_ANALYTICS_ADMIN_EMAIL=you@your-business-domain.example
```

Do not set this to a recipient/marketing email unless that is the intended administrator's
actual verified SkillLens login. Redeploy/restart the service after changing Render env.

While signed into that account, open:

- `https://skilllens-beta.onrender.com/analytics` — private dashboard
- `https://skilllens-beta.onrender.com/api/analytics/summary?days=30` — JSON counts

When the environment variable is absent or your SkillLens email is different, these
reporting endpoints return 404. Never expose raw database credentials to access metrics.

## What gets measured

Anonymous daily counts, **not unique users**:

- Page views (only allowlisted page paths)
- Successful free previews and full analyses
- Signup starts/submissions, login, upgrade clicks
- Checkout starts and follow-up client confirmation events
- Rewrites and quota exhaustion
- Allowlisted marketing channel from `utm_source` (whatsapp, telegram, linkedin, x,
  email, instagram, youtube, reddit; otherwise direct/other)

Campaign links can use `?utm_source=whatsapp`, `?utm_source=x`,
`?utm_source=linkedin`, etc. Only the whitelisted channel is sent/stored;
URL query strings and specific referral links are **not** collected.

## Privacy by design

- No consent banner. No GA4/Google tag load. No first- or third-party analytics cookies.
- The browser sends POSTs using `credentials: 'omit'`: no auth cookies or user IDs.
- Only strict enum event/page/source/feature/channel fields are accepted; unknown
  keys are rejected. No resume/JD text, email addresses, raw URL queries,
  IP address, device fingerprint or referrer is persisted in the metrics table.
- Existing decline choices are honored. Browser DNT/GPC and a privacy-page opt-out
  stop the event sends. Legacy GA4 `_ga*` cookies are cleared when possible.
- Data is aggregated by UTC day and deleted after 90 days by the retention job.
- Hosting/security systems may still process normal request metadata separately.

This approach is **not** a way to bypass applicable law; perform a privacy/legal review
before international expansion. The counters are easy to skew with bots, browser blockers
or repeated events and should not be considered audited traffic statistics.

## QA and operations

- CI: Python end-to-end and security tests, JS behavioral tests, Docker build.
- New incognito browser: no analytics permission prompt appears.
- Visit home, builder, privacy: `POST /api/analytics/event` with small whitelisted JSON.
- With DNT/GPC or previous decline preference: no event POSTs.
- Verify `_ga` analytics cookies are not created.
- With the Render admin email configured and signed in, check dashboard /analytics.
- Confirm unverified/non-admin visitors cannot access metrics.
- Sanity check numbers and channel counts after generating legitimate test traffic.
- Note dashboard does **not** report distinct people, country, GA4 sessions, or
  revenue reconciliation. Payment truth remains server-side Razorpay records.
- If the dashboard stays empty: inspect Render app logs and DB availability, confirm
  the deployment has the new `daily_metrics` table and script asset version.
