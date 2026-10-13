# Razorpay Standard Web Checkout — TEST MODE

This is a one-time Orders API **test** flow, separate from SkillLens's existing recurring subscription integration. **Successful verification DOES NOT unlock Pro**. Never advertise it as a Pro plan purchase.

## Stack & implementation

- FastAPI backend, server-side Razorpay REST using existing httpx-based `razorpay()` client (no duplicate SDK installation).
- Original encrypted user-account sessions and CSRF enforcement reused.
- Client-side JavaScript Checkout modal with success, failed payment, cancel and explicit verification handling.
- SQLAlchemy `checkout_orders` table + additive Alembic `0003` migration tracks ownership/price/idempotency.
- `POST /api/create-order` requires logged-in verified user, CSRF and exact server-configured INR amount (minimum 100 paise).
- `POST /api/verify-payment` validates HMAC-SHA256, checks owning user/order and fetches payment from Razorpay to require `captured`, before recording success.
- A failed/missing signature or uncaptured payment never marks an order as paid.
- Both existing subscription billing and Pro entitlements remain unchanged.

## Environment

**Do not commit a real `.env` or paste credentials into code or chat.**

Copy `.env.example` for local development and fill SECRET values privately:

```dotenv
RAZORPAY_KEY_ID=rzp_test_REPLACE_ME
RAZORPAY_KEY_SECRET=ROTATED_TEST_SECRET_FROM_RAZORPAY
SKILLLENS_STANDARD_CHECKOUT_ENABLED=true
SKILLLENS_STANDARD_TEST_AMOUNT_PAISE=100
```

For Render, set the same variables in Web Service → Environment. The app dynamically exposes a test checkout card when enabled; keep `SKILLLENS_LAUNCH_MODE=render_beta` and do **not** switch on live subscriptions to test Standard Checkout.

The API key secret shared in chat should be regarded as exposed. Regenerate it in Razorpay Test Mode before using it with Render.

## Tests

GitHub CI: `pytest -q` and Docker build.

Manual:
1. Open SkillLens, register/verify/login.
2. Find **Razorpay Test Checkout** at the pricing area; button opens modal.
3. Test with Razorpay's sandbox instructions; do not enter real card secrets in public screenshots.
4. On success, server confirms HMAC and fetches captured payment; message says no Pro upgrade.
5. Try closing modal, a failed payment and a tampered signature; no success should be reported.
6. Verify payment/order status in Razorpay Test Mode dashboard. Confirm account stays Free.

You can disable the feature instantly by setting `SKILLLENS_STANDARD_CHECKOUT_ENABLED=false` and redeploying.

## Production caution

A one-time order is not a recurring Pro subscription. Actual paid Pro billing needs merchant approval, real pricing/refunds/terms, completed subscription webhooks, reconciled entitlements and reliable paid hosting. This test checkout is intentionally limited to Razorpay `rzp_test_` keys.
