# PayU Online Payment Setup

This pharmacy app supports **PayU** for customer online payments on saved bills (Billing → Save Bill → **Pay Online**).

## 1. Get PayU credentials

1. Log in to [PayU Merchant Dashboard](https://onboarding.payu.in/app/account/login).
2. Open **Payment Gateway** → **System Details** (or **API Keys**).
3. Copy:
   - **Merchant Key** (e.g. `gtKFFx`)
   - **Salt** (32-character secret — never expose in frontend)

Use **Test** credentials first; switch to **Production** when going live.

## 2. Configure backend

Create or edit `backend/.env`:

```env
# PayU
PAYU_MERCHANT_KEY=your_merchant_key
PAYU_MERCHANT_SALT=your_merchant_salt
PAYU_ENV=test
PAYU_SUCCESS_URL=http://localhost:4000/payment/success
PAYU_FAILURE_URL=http://localhost:4000/payment/failure
FRONTEND_URL=http://localhost:4000

# Pharmacy details (shown on GST invoice PDF)
PHARMACY_NAME=Your Pharmacy Name
PHARMACY_GSTIN=27XXXXXXXXXXXZ5
PHARMACY_LICENSE=DL-XX-XXXX
PHARMACY_ADDRESS=Shop address, City, State PIN
PHARMACY_PHONE=+91-9876543210
PHARMACY_EMAIL=billing@yourpharmacy.com
```

Restart the backend after saving:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

## 3. PayU dashboard URLs

In PayU dashboard, set:

| Setting | Value (local dev) |
|--------|-------------------|
| Success URL | `http://localhost:4000/payment/success` |
| Failure URL | `http://localhost:4000/payment/failure` |
| Webhook / Callback (optional) | `https://YOUR_PUBLIC_URL/api/payments/payu/callback` |

For **local webhook testing**, use [ngrok](https://ngrok.com) to expose port 8001:

```powershell
ngrok http 8001
```

Then set callback URL to: `https://xxxx.ngrok.io/api/payments/payu/callback`

## 4. How billing + PayU works

1. Add items on **Billing** (`/billing`).
2. Set customer name, optional email (recommended for PayU).
3. Choose payment **Online** (or save as Cash/UPI first, then pay online).
4. Click **Save Bill** — stock is deducted; bill is stored with `payment_status: pending` if Online.
5. Click **Pay Online (PayU)** — browser posts to PayU checkout.
6. After payment, PayU redirects to `/payment/success` or `/payment/failure`.
7. Callback updates the bill: `paid_amount = grand_total`, `payment_status = paid`.

## 5. Test cards (PayU test mode)

Use PayU’s test documentation for current test card/UPI numbers. Typical test flow uses `PAYU_ENV=test` and `https://test.payu.in/_payment`.

## 6. Production checklist

- [ ] Switch `PAYU_ENV=production`
- [ ] Use live Merchant Key + Salt
- [ ] HTTPS on frontend and backend
- [ ] Update `PAYU_SUCCESS_URL` / `PAYU_FAILURE_URL` to your live domain
- [ ] Register webhook URL with PayU
- [ ] Verify GST invoice PDF: `pip install reportlab` in backend venv

## 7. API reference (for developers)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/billing/invoice-settings` | GET | Pharmacy header for invoice |
| `/api/invoices/sale/{id}/pdf` | GET | GST invoice PDF |
| `/api/payments/payu/status` | GET | Is PayU configured? |
| `/api/payments/payu/init` | POST | Start payment `{ "sale_id": "..." }` |
| `/api/payments/payu/callback` | POST | PayU return (form POST) |
| `/api/payments/payu/verify/{txnid}` | GET | Check transaction status |

## 8. Troubleshooting

| Issue | Fix |
|-------|-----|
| PayU button hidden | Set `PAYU_MERCHANT_KEY` and `PAYU_MERCHANT_SALT` in `.env`, restart backend |
| Invalid hash | Salt must match PayU dashboard exactly |
| PDF download fails | `pip install reportlab` in `.venv` |
| Payment success but bill still pending | Ensure callback URL is reachable; check `/api/payments/payu/verify/{txnid}` |

For PayU support: [PayU Developer Docs](https://docs.payu.in/)
