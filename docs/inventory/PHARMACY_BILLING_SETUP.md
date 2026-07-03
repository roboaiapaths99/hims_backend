# Pharmacy Billing + Inventory Module — Setup Guide

Built on your existing **FastAPI + Next.js + MongoDB** stack (not a separate Node.js app).

## Quick start

### 1. Backend

```bash
cd backend
# Activate venv from project root if needed
..\.venv\Scripts\activate
pip install -r requirements.txt
# Configure MongoDB in backend/.env
python scripts/seed_billing_data.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:4000/billing** for counter billing.

### 3. Import your stock_81 dataset (permanent database storage)

```bash
cd backend
python scripts/import_stock_json_to_db.py          # all 2345 medicines + batches for in-stock items
python scripts/import_stock_json_to_db.py --stock-only   # only 831 items with stock (faster billing)
```

Or in the UI: **Inventory → Import Data** → **Import all to database**

Data is stored in MongoDB collections `medicines` and `medicine_batches` with fields:
medicine name, salt/generic, company/category, manufacturer, barcode/import code, HSN, GST, unit, rack, MRP, purchase price, selling price, batch qty.

### 4. Login (production)

- Register/login: `POST /api/auth/login`
- Default seed admin: **admin@pharmacy.com** / **admin123**
- In `DEBUG=true`, billing APIs work without a token (uses first admin user).

Store token in browser: `localStorage.setItem('pharmacy_token', '<jwt>')`

## New API routes

| Module | Endpoints |
|--------|-----------|
| Customers | `GET/POST/PUT/DELETE /api/customers`, `GET /api/customers/{id}/history` |
| Purchases | `GET/POST /api/purchases`, `GET /api/purchases/{id}` |
| Billing | `GET /api/billing/search?q=`, `GET /api/billing/fefo/{medicineId}?quantity=` |
| Sales | `POST /api/sales`, `GET /api/sales/invoice/{invoiceNumber}` |
| Returns | `POST /api/sales-return`, `POST /api/purchase-return` |
| Dashboard | `GET /api/dashboard/summary`, `daily-sales`, `monthly-sales`, `top-selling`, `low-stock`, `expiry-alerts` |
| Reports | `GET /api/reports/sales`, `purchase`, `stock`, `gst`, `profit`, `customer-dues`, `supplier-dues` |

## Frontend pages

| Route | Purpose |
|-------|---------|
| `/billing` | Fast POS billing, FEFO, print invoice |
| `/medicines` | Medicine master CRUD |
| `/batches` | Batch-wise stock |
| `/purchase` | Purchase entry |
| `/sales-return` | Sales return |
| `/purchase-return` | Purchase return |
| `/reports/*` | Sales, stock, expiry, GST, profit |
| `/dashboard` | Live summary (connected to new APIs) |

## Business logic

- **FEFO**: Batches sorted by expiry; nearest expiry sold first (`fifo_service.py` / `billing_service.py`).
- **Expired batches**: Blocked at sale time.
- **Billing math**: `subtotal = qty × selling_price`, discount %, GST on taxable amount, `final = taxable + gst`.
- **Stock**: Purchase increases batch qty; sale increases `quantity_sold`; returns reverse both.
- **Credit sales**: `payment_method: Credit`, `paid_amount` + `due_amount` update customer record.

## Example test sale (API)

```json
POST /api/sales/
{
  "customer_name": "Ravi",
  "customer_phone": "9876543210",
  "payment_method": "Cash",
  "paid_amount": 0,
  "items": [{
    "medicine_id": "<medicine_id>",
    "medicine_name": "Paracetamol 500mg",
    "quantity": 2,
    "selling_price": 40,
    "gst_percentage": 12,
    "hsn_code": "30049099"
  }]
}
```

## Database collections

- `medicines`, `medicine_batches`, `suppliers`, `customers`
- `purchase_invoices`, `sales`, `sales_returns`, `purchase_returns`
- `stock_ledger`, `users`
