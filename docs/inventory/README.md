# Pharmacy ERP - Complete Inventory Management System

A production-grade Pharmacy/Chemist Inventory Management System built for Indian retail pharmacies and medical distributors. Comparable to Marg ERP, GOFRUGAL, and Zoho Inventory.

## Features

- **Complete Medicine Lifecycle**: Procurement, batch tracking, sales/billing, expiry monitoring
- **GST Compliance**: Automated GST calculations, invoice generation, and reporting
- **Multi-Store Support**: Stock transfers between warehouses with approval workflows
- **Barcode Integration**: ZXing-based barcode scanning for quick medicine lookup
- **AI-Powered Forecasting**: Demand prediction using Prophet/scikit-learn
- **Role-Based Access Control**: Admin, Store Manager, Pharmacist, Cashier roles
- **Audit Logging**: Complete audit trail for all transactions
- **Schedule Drug Compliance**: H and X schedule drug regulations enforcement

## Tech Stack

- **Backend**: FastAPI (Python 3.11+), MongoDB Atlas, Celery + Redis
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Deployment**: Docker, Nginx, AWS/DigitalOcean
- **AI/ML**: Prophet for demand forecasting

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB Atlas account
- Redis server

### Backend Setup
```bash
cd backend
cp .env.example .env
# Edit .env with your configuration
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

- Backend URL: `http://localhost:8002`
- Swagger docs: `http://localhost:8002/docs`

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Run in VS Code
If you use Visual Studio Code, open the workspace and run these tasks from the Command Palette (`Ctrl+Shift+P`):
- `Tasks: Run Task` → `Start Backend`
- `Tasks: Run Task` → `Start Frontend`
- `Tasks: Run Task` → `Start Backend + Frontend`

### Docker Deployment
```bash
docker-compose up -d
```

## Project Structure

```
pharmacy_erp/
|-- backend/
|   |-- api/           # API endpoints
|   |-- models/        # MongoDB models
|   |-- services/      # Business logic
|   |-- tasks/         # Celery tasks
|   |-- middleware/    # Custom middleware
|   |-- main.py        # FastAPI app entry
|   |-- config.py      # Configuration
|   |-- database.py    # Database connection
|   |-- requirements.txt
|   |-- .env.example
|
|-- frontend/
|   |-- app/           # Next.js pages
|   |-- components/    # React components
|   |-- lib/           # Utility functions
|   |-- package.json
|   |-- tailwind.config.js
|
|-- docker/
|   |-- Dockerfile.backend
|   |-- Dockerfile.frontend
|   |-- docker-compose.yml
|
|-- docs/
|   |-- api_reference.md
```

## Key Business Rules

- **FIFO Sales**: Always use First-In-First-Out batch selection
- **Schedule Drug Compliance**: H and X schedule drugs require prescription/ID proof
- **Stock Validation**: Stock can never go negative
- **Audit Trail**: Every stock movement creates a ledger entry
- **GRN-PO Link**: Goods Receipt must be linked to Purchase Order
- **Transfer Approval**: Stock transfers require store manager approval

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## License

MIT License - see LICENSE file for details
