"""Legal copy is a launch checklist starting point, not legal advice."""
import html
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


def page(title, content):
    operator = html.escape(os.getenv('LEGAL_OPERATOR', '[Business legal name required]'))
    email = html.escape(os.getenv('LEGAL_CONTACT_EMAIL', '[Support email required]'))
    address = html.escape(os.getenv('LEGAL_POSTAL_ADDRESS', '[Postal address required]'))
    updated = html.escape(os.getenv('LEGAL_UPDATED', '13 October 2026'))
    advisory = '' if os.getenv('LEGAL_REVIEWED') == 'yes' else '<hr><p>This policy template must be reviewed and customized for your business and applicable laws before accepting paying customers.</p>'
    return HTMLResponse('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+html.escape(title)+''' — SkillLens</title><link rel="stylesheet" href="/assets/styles.css"></head><body><main class="shell" style="max-width:850px;padding:45px 15px;line-height:1.8"><p><a href="/">← Back to SkillLens</a></p><h1>'''+html.escape(title)+'''</h1><p>Last updated: '''+updated+'''</p><p><strong>Service operator:</strong> '''+operator+''' · <strong>Contact:</strong> '''+email+''' · <strong>Address:</strong> '''+address+'''</p>'''+content+advisory+'''</main></body></html>''')


@router.get('/privacy', include_in_schema=False)
def privacy():
    beta_notice = ('For this beta, generative external AI and live subscription charges are not enabled. '
                   'A clearly labeled Razorpay sandbox checkout may be available for simulation without real charges.'
                   if os.getenv('SKILLLENS_LAUNCH_MODE', '').lower() == 'render_beta'
                   else 'Paid subscriptions may be processed by Razorpay under its own policies. '
                        'Only the plan and checkout disclosures shown at purchase apply; '
                        'users can request cancellation from their account.')
    return page('Privacy policy', '''
<h2>Information we collect</h2><p>For accounts: email address, password hash, sessions, plan and feature usage. For analyses: resumes and job descriptions that you submit are processed in server memory. Raw upload files are not intentionally persisted to application storage. Your generated report is saved only if you select Save, encrypted at rest by the application. Saved reports become inaccessible after 30 days. Expired records are purged on application startup and approximately daily while the service is running; infrastructure backups may retain copies for their provider's configured period.</p>
<h2>Purpose</h2><p>We use this information to authenticate, generate resume-to-job feedback, enable billing, prevent abuse, and respond to support requests. Reports are not employer hiring decisions, applicant tracking system scores or guaranteed predictions.</p>
<h2>Third-party services</h2><p>If you explicitly select an external AI provider, redacted resume evidence and job-description excerpts may be sent to the configured provider; redaction cannot guarantee anonymity. Razorpay may process payment details under its own terms and privacy policies; SkillLens does not receive your card numbers. SkillLens uses Render (application hosting), Neon (PostgreSQL database), and Brevo (transactional email); those providers process data needed to operate the service. ''' + beta_notice + ''' The operator must confirm and publish actual subprocessors and any applicable international data transfer details before wider public rollout.</p>
<h2>Retention, security and rights</h2><p>We protect login sessions with HTTP-only cookies, hash passwords with Argon2, and encrypt optional reports at rest. No internet service can guarantee perfect security. You can delete saved reports and close your account from the account dialog (active subscriptions must first be cancelled). Some provider records may be retained separately under payment, accounting or legal obligations. You may contact the operator to request access, correction or other rights available under applicable law.</p>
<h2>Browser-based document import and availability</h2><p>When supported, PDF/DOCX/TXT files are read by the browser, and extracted text is submitted to the analysis API. Raw file uploads to the hosted backend are disabled. The service currently uses a free hosting tier that can sleep when idle and restart unexpectedly; availability and immediate paid-plan activation cannot be guaranteed. Contact support if a confirmed payment does not unlock access.</p>
<h2>Cookies</h2><p>We use an essential first-party login session cookie. We do not enable tracking advertising cookies in this release.</p>
<h2>Changes</h2><p>We may revise this policy when the service changes; material changes should be announced to users.</p>
''')


@router.get('/terms', include_in_schema=False)
def terms():
    is_beta = os.getenv('SKILLLENS_LAUNCH_MODE', '').lower() == 'render_beta'
    subscriptions = ('''<h2>Free beta</h2><p>SkillLens is currently a no-payment beta. The free plan allows five analyses and three rewrites per UTC calendar month. Paid checkout and Pro subscriptions are disabled until the operator publishes final merchant, payment, cancellation, tax and refund details. The availability of any future paid offering is not guaranteed.</p>'''
                     if is_beta else '''<h2>Plans and recurring subscription</h2>
<p>The Free plan provides 5 job-match analyses, 3 resume rewrites, and up to 5 saved reports each UTC calendar month. SkillLens Pro is INR 199 per monthly billing cycle for up to 12 cycles, with 200 analyses, 100 rewrites, and up to 100 saved reports. This is recurring billing, not a one-time purchase or unlimited-use plan. Renewal after the 12th cycle is not automatic without a newly authorized subscription. Any applicable taxes or additional charges must be disclosed by the payment checkout before authorization. There is no guaranteed employment outcome.</p>
<h2>Authorisation, payment, and access</h2>
<p>Razorpay administers payment authorisation and scheduled debits. Pro access starts only when Razorpay confirms an active, paid subscription period. Completing a payment mandate or opening Checkout does not itself activate Pro. If access is delayed after a successful charge, sign in and use Refresh billing status or contact the operator using the support address above. The hosted service can experience cold starts or interruptions.</p>
<h2>Cancellation and renewal</h2>
<p>You may request cancellation inside your account at any time. SkillLens sends a request to Razorpay to cancel at the end of the current billing cycle; the merchant will confirm cancellation with Razorpay. A verified paid period ordinarily remains available until it ends, and no further cycle should be charged after effective cancellation. If cancellation cannot be completed in-app, contact the support email above before the next billing date. Closing your account requires confirmation that the subscription has ended.</p>
<h2>Refund and payment disputes</h2>
<p>If you are charged twice, charged in error, or charged without receiving Pro access, contact the support address above with your Razorpay payment reference. The operator will investigate and arrange correction or a refund when verified and appropriate. Other refund requests are assessed case by case, including actual usage, payment processing status, and applicable consumer law. Requesting cancellation alone does not automatically reverse an already billed period. Any approved refund is processed through Razorpay and the original payment provider, subject to their processing time. Nothing here restricts mandatory statutory remedies.</p>
<h2>Consumer support</h2><p>Billing, subscription cancellation, and refund queries: contact the support email stated at the top of this page. Include the account email and payment reference, but never share your card details, passwords, or payment secrets.</p>''')
    return page('Terms of service', '''
<h2>Service</h2><p>SkillLens provides automated resume analysis and drafting assistance. Scores are model estimates and are not official ATS scores, hiring probabilities, professional qualifications or employment advice. Review and verify all suggestions yourself. Do not submit third-party personal documents without permission.</p>
<h2>Account and acceptable use</h2><p>You must provide a valid email and protect your password. Automated abuse, attempts to access other users' data, illegal use and excessive traffic are prohibited. Users remain responsible for their own application content.</p>
''' + subscriptions + '''
<h2>Availability and liability</h2><p>The service may be unavailable during maintenance or third-party outages. AI-generated language may contain inaccuracies. Nothing guarantees interviews, employment or acceptance by an employer. Mandatory consumer rights under applicable law are not waived by these terms.</p>
<h2>Account closure</h2><p>You can request deletion from your account. If you have an active subscription, request cancellation and wait for provider confirmation before closing the account. The operator must supply a separate support route for disputes or deletion obstacles.</p>
''')
