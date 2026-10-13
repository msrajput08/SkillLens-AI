# SkillLens release checklist (complete BEFORE public launch)

## Business and payments
- [ ] Verify real legal operator identity, postal/support details, contact email, business documents, merchant eligibility.
- [ ] Approve real Privacy Policy, Terms of Service, Cancellation/Refund Policy, taxes/GST and consumer rights with qualified counsel.
- [ ] Configure Razorpay plan and exact INR/month pricing; reconcile server configuration to merchant dashboard.
- [ ] Configure Razorpay test subscriptions; verify authorization, active, renewal, payment failures, cancellations, webhook duplicates, missing events, test-to-live keys and support refunds.
- [ ] Ensure real plan charge matches published website price; never accept money while published information is incomplete.

## Technology and operations
- [ ] DNS, HTTPS, firewall, server security patching and external backups (encrypted and restore-tested).
- [ ] Secret management, key rotation playbook and disaster recovery plan.
- [ ] SMTP delivery with SPF/DKIM/DMARC, account verification and password reset tested with real inboxes.
- [ ] ClamAV signature updates and malware upload test; throttle/abuse protection and load test.
- [ ] Confirm .env.production secrets; no placeholders or test keys.
- [ ] Real AI model installation/benchmark and external-provider privacy agreement if offered.
- [ ] Legal review for AI resume advice, privacy compliance and data deletion.
- [ ] Add monitoring, uptime alerts, safe logs, breach/incident response and customer-support workflows.
- [ ] Validate privacy policy and cancellation portal URLs in live browser, mobile and desktop.

## QA gates
- [x] Automated API & security tests pass in local environment.
- [x] Frontend renders in isolated Chromium desktop/mobile without JS errors.
- [x] Account signup/signin, encrypted report isolation and quota checks tested with local TestClient.
- [x] Webhook HMAC rejection, simulated activation/cancellation and duplicate event tests pass.
- [ ] Full hosted E2E signup → SMTP verify → upload → live paid subscription → cancel → deletion.
- [ ] Production Docker build, HTTPS and real provider connectivity confirmed.
- [ ] Third-party penetration testing and launch sign-off.

## Product roadmap after initial SaaS launch
- Email change + MFA, professional resume editor with visual templates and PDF export, verified native integrations to job listings, admin/support dashboard, invoice/tax handling, feature analytics with consent, unit-cost monitoring, institutional team plans, genuine human-evaluated fine-tuning experiments and improved accessibility.
