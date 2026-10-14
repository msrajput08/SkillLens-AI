# SkillLens AI — Public Paid Beta Launch
**Launch date:** 14 October 2026

**Website:** https://skilllens-beta.onrender.com

## What is available
- Free: 5 job-match analyses and 3 resume rewrites per UTC calendar month, up to 5 saved reports.
- Pro: ₹199 INR per month, up to 12 authorized billing cycles; 200 analyses, 100 rewrites and up to 100 saved reports per month. See the actual Razorpay mandate and checkout terms for authorisation, taxes, and dates.
- Resume-to-job matching and evidence-based feedback, safe resume rewriting, document export, a browser resume builder, encrypted personal workspaces, saved reports and an application tracker.
- Browser-side PDF/DOCX/TXT import. The hosted backend disables raw file uploads.

## Payment readiness
- Razorpay Live ₹199 INR monthly plan verified through a read-only authenticated API request from the deployed application.
- Live subscription Checkout, signed callback confirmation, webhooks, idempotent events, provider-side verification of paid periods, and end-of-cycle cancellation are implemented.
- The operator personally reported a successful real payment and Pro activation. This is **not** a substitute for ongoing monitoring and independent payment or security audits.
- The ₹1 Razorpay sandbox checkout is disabled on the live paid-beta configuration.

## Reliability and important limitations
- Render Free and Neon Free are used to avoid fixed monthly hosting charges. Render Free may spin down after inactivity. Payment webhooks can be delayed and subscription entitlements may take time to reconcile. Users can click **Refresh billing status** after signing in and contact the operator for unresolved charges.
- No uptime SLA, independently certified security review, production-grade incident response, or fully rehearsed recovery procedure is claimed.
- Job-match scoring is a decision-support estimate, **not** an employer ATS score, hiring probability, or job guarantee.
- Merchant compliance, applicable taxes, refund/cancellation processes, restoration tests and backup retention are still operational responsibilities. Public policies: [Terms](https://skilllens-beta.onrender.com/terms) and [Privacy](https://skilllens-beta.onrender.com/privacy).

## Rollback and support
If real payments or entitlements become unreliable, disable new purchases via Render `SKILLLENS_PRO_BILLING_ENABLED=false` while maintaining signed webhook handling and customer reconciliation for existing subscriptions. **Never** disable or discard subscription records solely by hiding the checkout button. Existing paying users must still be supported or appropriately refunded if required.

The website's account dialog includes **Refresh billing status** and subscription cancellation. For payment disputes use the legal contact address published on the live site's Terms page.
