# Pharmacy Inventory Management System - Complete User Guide

## Table of Contents
1. [Getting Started](#getting-started)
2. [System Requirements](#system-requirements)
3. [Installation & Setup](#installation--setup)
4. [Login & User Roles](#login--user-roles)
5. [Dashboard Overview](#dashboard-overview)
6. [Core Features & How to Use](#core-features--how-to-use)
7. [Common Workflows](#common-workflows)
8. [Tips & Best Practices](#tips--best-practices)
9. [Troubleshooting](#troubleshooting)
10. [Support & Contact](#support--contact)

---

## Getting Started

Welcome to the **Pharmacy Inventory Management System** – a complete solution for managing your pharmacy's stock, sales, purchases, and compliance requirements. This guide will help you set up and use the system effectively.

### What is This System?

This is an enterprise-grade inventory management software designed specifically for Indian pharmacies and medical distributors. It helps you:
- Manage medicine stock across multiple stores
- Process sales and billing automatically
- Track purchase orders and goods receipts
- Monitor medicine expiry dates
- Generate compliance reports
- Calculate GST automatically
- Track audit trails for all transactions

---

## System Requirements

### For Customers (End Users)

**Minimum Requirements:**
- **Internet Connection**: Stable broadband connection (4+ Mbps recommended)
- **Browser**: 
  - Google Chrome (latest version)
  - Mozilla Firefox (latest version)
  - Microsoft Edge (latest version)
  - Safari (latest version)
- **Computer/Device**:
  - Windows 7 or later
  - macOS 10.12 or later
  - Linux (Ubuntu 18.04+)
  - Tablet/iPad (iOS 12+)
  - Android Device (Android 8.0+)
- **Screen Resolution**: Minimum 1024x768 (1920x1080 recommended)

**Network Requirements:**
- Access to ports 80 and 443
- Firewall configured to allow application traffic

### For Server/Deployment

**Server Requirements (if self-hosting):**
- OS: Ubuntu 18.04 LTS or Windows Server 2016+
- CPU: 2 cores minimum, 4 cores recommended
- RAM: 4GB minimum, 8GB recommended
- Disk Space: 50GB for database + 20GB for files
- Python 3.11+
- Node.js 18+
- Docker (optional, for containerization)

**External Services Needed:**
- MongoDB Atlas account (cloud database)
- Redis server (for background jobs)
- Email service (Gmail or similar for alerts)

---

## Installation & Setup

### Step 1: For Hosted Version (Recommended for Most Users)

**If your system is hosted by a provider:**

1. **Receive Access Credentials**
   - You'll receive an email with login details
   - Username/Email and temporary password
   - System URL (e.g., http://yourpharmacy.com:4000)

2. **First Login**
   - Open the system URL in your browser
   - Enter your credentials
   - Change your password on first login
   - Complete your user profile

### Step 2: For Self-Hosted Version

**Prerequisites:**
- Python 3.11+ installed
- Node.js 18+ installed
- MongoDB Atlas account created
- Redis server running

**Installation Steps:**

```bash
# 1. Clone or extract the project files
cd AGPK0NE_INVENTRY_ANAGEMENT

# 2. Backend Setup
cd backend
cp .env.example .env

# Edit .env file with your configuration:
# - MONGODB_URI: Your MongoDB connection string
# - JWT_SECRET: A secure random key
# - PHARMACY_NAME, GSTIN, LICENSE: Your pharmacy details
# - SMTP settings: For email notifications

pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Frontend Setup (in new terminal)
cd frontend
npm install
npm run dev --port 4000

# 4. Access the application
# Open browser: http://localhost:4000
```

**Using Docker (Easiest):**

```bash
docker-compose up -d
# Application will be available at http://localhost:4000
```

---

## Login & User Roles

### Default Roles

The system supports multiple user roles, each with specific permissions:

| Role | Responsibilities | Access Level |
|------|-----------------|--------------|
| **Admin** | System configuration, user management, pharmacy settings | Full access |
| **Store Manager** | Inventory oversight, approve transfers, generate reports | High access |
| **Pharmacist** | Process sales, check stock, dispense medicines | Medium access |
| **Cashier** | Process bills and payments at POS | Limited access |
| **Warehouse Staff** | Receive goods, process transfers | Limited access |

### How to Login

1. Open the application URL in your browser
2. Enter your **Email/Username**
3. Enter your **Password**
4. Click **Login**
5. If you forgot your password, click **"Forgot Password"** and follow the recovery steps

### First-Time Setup

1. **Change Default Password**
   - On first login, you'll be prompted to change your password
   - Use a strong password (min 8 characters, mix of letters, numbers, special characters)

2. **Complete Profile**
   - Add your phone number
   - Set your store/location preference
   - Enable two-factor authentication (optional but recommended)

---

## Dashboard Overview

The **Dashboard** is your command center when you log in.

### Dashboard Components

**1. Key Metrics Section**
- **Total Stock Value**: Current inventory value at cost price
- **Low Stock Items**: Medicines needing reorder
- **Expiring Soon**: Items expiring within 30 days
- **Today's Sales**: Total revenue today
- **Pending Approvals**: Actions requiring your approval

**2. Charts & Graphs**
- **Sales Trend**: Last 7 days sales chart
- **Top Selling Medicines**: Best performers
- **Stock Distribution**: By medicine category
- **Expiry Timeline**: Graphical expiry tracking

**3. Quick Actions**
- Add New Medicine
- Process Sale
- Create Purchase Order
- Process GRN (Goods Receipt Note)
- Stock Transfer

**4. Recent Activities**
- Latest transactions
- Recent stock movements
- User activities

**5. Notifications**
- Low stock alerts
- Expiring medicine warnings
- Pending approvals
- System updates

---

## Core Features & How to Use

### 1. INVENTORY MANAGEMENT

**Access**: Sidebar → Inventory

#### 1.1 View Stock

1. Click **"Inventory"** in sidebar
2. Select **"Stock Management"**
3. View all medicines with:
   - Medicine name and code
   - Current quantity on hand
   - Reorder level
   - Unit price
   - Batch information
   - Expiry date

**Filters Available:**
- By Category (Tablets, Injections, Syrups, etc.)
- By Status (Low Stock, Expired, Expiring Soon)
- By Supplier
- By Batch

#### 1.2 Add New Medicine

1. Click **"Inventory"** → **"Add New Medicine"**
2. Fill required fields:
   - **Medicine Name**: Exact name (e.g., "Paracetamol 500mg")
   - **Medicine Code**: Unique code (e.g., "PARA500")
   - **Generic Name**: Generic composition
   - **Manufacturer**: Manufacturing company
   - **Category**: Select from dropdown (Tablet, Injection, Syrup, etc.)
   - **Unit**: Pieces, Strips, Bottles, etc.
   - **HSN Code**: For GST calculation
   - **Reorder Level**: Quantity to trigger reorder
   - **Reorder Quantity**: Amount to order when triggered
3. Click **"Save Medicine"**

#### 1.3 Update Stock Manually

1. Click **"Inventory"** → **"Adjustment"**
2. Select the medicine to adjust
3. Enter **Current Quantity** shown in system
4. Enter **Corrected Quantity** (physical count)
5. Reason (Damage, Loss, Physical Count, etc.)
6. Click **"Submit Adjustment"**

#### 1.4 Track Expiry Dates

1. Click **"Inventory"** → **"Expiry Tracking"**
2. View all medicines with expiry information:
   - **Expiring Soon** (< 30 days): Red highlight
   - **Expiring Soon** (30-60 days): Yellow highlight
   - **Valid Stock**: Green
3. Click on any item to see:
   - Batch numbers
   - Manufacturing date
   - Expiry date
   - Quantity per batch

**Alert System:**
- System automatically alerts 90 days before expiry
- Cannot sell expired medicines
- Automatic hold on expired batches

---

### 2. PURCHASE ORDERS & GOODS RECEIPT

**Access**: Sidebar → Purchase Orders

#### 2.1 Create Purchase Order (PO)

1. Click **"Purchase Orders"** → **"New Purchase Order"**
2. Fill details:
   - **Select Supplier**: Choose from supplier list
   - **PO Date**: Today's date (auto-filled)
   - **Expected Delivery Date**: When you expect goods
   - **Delivery Address**: Your store address (can be changed)

3. Add medicines to order:
   - Click **"Add Medicine"**
   - Select medicine from list
   - Enter **Quantity to Order**
   - System auto-fills unit price
   - Enter **Tax Rate** (GST %)
   - Click **"Add to Order"**

4. Review Summary:
   - Subtotal
   - Tax amount
   - Total amount

5. Click **"Create Purchase Order"**
   - System generates PO number
   - Send to supplier (email/WhatsApp/Phone)

#### 2.2 Process Goods Receipt (GRN)

When goods arrive:

1. Click **"Purchase Orders"** → **"Receive Goods"**
2. Select the **Purchase Order** to receive against
3. System shows items ordered vs. arriving
4. For each medicine:
   - Enter **Quantity Received** (may differ from ordered)
   - Enter **Batch Number**
   - Enter **Manufacturing Date**
   - Enter **Expiry Date**
   - Verify **Unit Price** (can edit if different)
5. Upload **Supplier Invoice** (PDF)
6. Add notes if needed (e.g., "2 bottles damaged")
7. Click **"Complete Receipt"**

**System Actions:**
- Updates stock automatically
- Creates batch records
- Links to Purchase Order
- Generates audit trail

---

### 3. SALES & BILLING (POS)

**Access**: Sidebar → POS or Sales

#### 3.1 Process Sale/Create Bill

**Method 1: Using Barcode Scanner**

1. Click **"POS"** (Point of Sale)
2. New bill form opens
3. **Scan barcode** of first medicine
   - Automatically adds to bill
   - Shows available stock
   - Shows price and tax
4. Enter **Quantity** if more than 1 unit
5. Repeat for all medicines
6. System automatically calculates totals

**Method 2: Manual Entry**

1. Click **"POS"**
2. Click **"Add Medicine"**
3. Search for medicine name or code
4. Select from results
5. Enter quantity
6. Click add
7. Repeat for other medicines

**Bill Summary:**
- Item-wise price breakdown
- Sub-total
- GST amount (calculated automatically)
- Total payable

#### 3.2 Apply Discounts

1. In bill form, click **"Discount"**
2. Choose:
   - **Percentage Discount**: Entire bill (e.g., 5%)
   - **Amount Discount**: Fixed amount (e.g., Rs. 100)
   - **Item Discount**: Specific medicine discount
3. Click apply

#### 3.3 Complete Sale

1. Select **Payment Method**:
   - Cash
   - Card
   - UPI/Mobile Wallet
   - Credit/Loan (if configured)
2. Enter amount received
3. System shows change due
4. Click **"Complete Sale"**

**After Sale:**
- Bill printed/displayed
- Stock updated automatically
- FIFO (First-In-First-Out) batch automatically selected
- Audit entry created

#### 3.4 View/Reprint Bill

1. Click **"Sales"** → **"Recent Transactions"**
2. Find the transaction
3. Click **"View"** to see details
4. Click **"Reprint Bill"** if customer needs duplicate

---

### 4. STOCK TRANSFERS (Multi-Store)

**Access**: Sidebar → Inventory → Transfers

#### 4.1 Initiate Transfer

1. Click **"Transfers"**
2. Click **"New Transfer"**
3. Fill details:
   - **From Store**: Your current store
   - **To Store**: Receiving store
   - **Expected Delivery**: When stock should arrive
4. Add medicines:
   - Click **"Add Item"**
   - Select medicine
   - Enter quantity
   - Select batch (if multiple batches)
5. Add **"Special Instructions"** if needed
6. Click **"Request Transfer"**
   - Notifies receiving store manager
   - Creates approval workflow

#### 4.2 Approve/Reject Transfer (Store Manager)

1. Click **"Dashboard"** (if pending)
   - Or go to **"Transfers"** → **"Pending Approvals"**
2. Review transfer details
3. Click **"Approve"** or **"Reject"**
   - If Reject: Add reason
4. If approved:
   - Stock deducted from sending store
   - Added to receiving store
   - Audit trail created

---

### 5. SUPPLIER MANAGEMENT

**Access**: Sidebar → Suppliers

#### 5.1 Add New Supplier

1. Click **"Suppliers"** → **"Add New Supplier"**
2. Fill details:
   - **Company Name**: Supplier's business name
   - **Contact Person**: Primary contact name
   - **Email**: supplier@example.com
   - **Phone**: Mobile number
   - **GST Number**: For tax purposes
   - **Address**: Full address
   - **Bank Details**: For payments (optional)
   - **Credit Terms**: Payment due days (e.g., 30 days)

3. Add **Payment Terms**:
   - Cash on Delivery (COD)
   - Credit (Net 30/60)
   - Partial Advance

4. Click **"Save Supplier"**

#### 5.2 View Supplier Details

1. Click **"Suppliers"** → **"View All"**
2. Select any supplier
3. View:
   - Contact information
   - Purchase history
   - Outstanding bills
   - Rating (based on delivery, quality)
   - Recent transactions

#### 5.3 Create Supplier Payment

1. From supplier detail page
2. Click **"Create Payment"**
3. Select invoices to pay (system groups by due date)
4. Enter **Payment Amount**
5. Select **Payment Method** (Check, Bank Transfer, Cash)
6. Click **"Record Payment"**

---

### 6. CUSTOMER MANAGEMENT

**Access**: Sidebar → Customers

#### 6.1 Add Retail Customer

For walk-in customers, basic information is captured:
1. System auto-creates record for billing
2. Optional: Enter phone number for loyalty tracking
3. System tracks:
   - Purchase history
   - Spending patterns
   - Frequent purchases

#### 6.2 Add Wholesale/Corporate Customer

1. Click **"Customers"** → **"Add Corporate Customer"**
2. Fill details:
   - **Business Name**
   - **Contact Person**
   - **Email**
   - **Phone**
   - **GST Number**
   - **Credit Limit**: Maximum credit allowed
   - **Payment Terms**: Credit days allowed
3. Click **"Save Customer"**

#### 6.3 View Customer History

1. Click **"Customers"** → **"View All"**
2. Select customer
3. View:
   - Purchase history
   - Total spent
   - Outstanding balance
   - Loyalty points (if enabled)

---

### 7. REPORTS & ANALYTICS

**Access**: Sidebar → Inventory → Reports

#### 7.1 Sales Report

1. Click **"Reports"** → **"Sales Analysis"**
2. Select **Date Range**:
   - Today
   - This Week
   - This Month
   - Custom Range
3. Filter by:
   - Cashier/User
   - Payment method
   - Medicine category
4. View:
   - Total sales value
   - Transaction count
   - Average bill value
   - Top medicines sold
   - Detailed transaction list
5. Click **"Export to Excel"** or **"Print"**

#### 7.2 Stock Report

1. Click **"Reports"** → **"Stock Analysis"**
2. View:
   - Stock value (cost price)
   - Quantity on hand vs. system
   - Stock movement (inward/outward)
   - Fast-moving items
   - Slow-moving items
   - Dead stock (no movement in 90 days)
3. Click **"Export to PDF"** for accounting

#### 7.3 Expiry Report

1. Click **"Reports"** → **"Expiry Report"**
2. View:
   - Expiring within 30 days
   - Already expired (auto-blocked)
   - Expiry timeline
3. Plan disposal/donation accordingly

#### 7.4 GST Report

1. Click **"Reports"** → **"GST Report"**
2. Useful for:
   - GST filing
   - Tax calculation verification
   - Monthly reconciliation
3. Select month/quarter
4. System calculates:
   - Total sales (taxable)
   - SGST collected
   - CGST collected
   - IGST (if inter-state)
   - ITC (Input Tax Credit)
5. Export for filing

---

### 8. ALERTS & NOTIFICATIONS

**Access**: Bell icon (top right)

#### Types of Alerts

1. **Low Stock Alert**
   - Medicine quantity falls below reorder level
   - Action: Create purchase order

2. **Expiry Alert**
   - Medicine expiring within 30 days
   - Action: Plan disposal or sale at discount

3. **Approval Pending**
   - Waiting for your approval (transfer, return, etc.)
   - Action: Review and approve/reject

4. **Payment Reminder**
   - Supplier payment due soon
   - Overdue customer invoices

5. **System Notifications**
   - Maintenance windows
   - Feature updates
   - Security alerts

---

## Common Workflows

### Workflow 1: New Day Start

**Every Morning:**

1. **Check Dashboard**
   - Review overnight transactions
   - Check for low stock alerts
   - Review pending approvals

2. **Count Opening Stock** (if required)
   - Physical verification
   - Report discrepancies

3. **Check Expiry Tracking**
   - Plan for expiring medicines
   - Mark for return/disposal if needed

4. **Review Alerts**
   - Address any system issues
   - Plan the day's purchases/orders

---

### Workflow 2: Receiving Stock

**When Goods Arrive:**

1. **Receive Purchase Order**
2. **Physical Verification**
   - Count items received
   - Check quality
   - Verify batch numbers and expiry dates
3. **Process GRN**
   - Enter actual received quantities
   - Upload supplier invoice
   - Add notes about any discrepancies
4. **Complete Receipt**
   - System updates stock
   - Notifies low-stock items for reorder

---

### Workflow 3: Processing a Sale

**When Customer Arrives:**

1. **Open POS**
2. **Add Medicines** (by scan or search)
3. **Apply Discount** (if any)
4. **Process Payment**
5. **Print Bill**
6. **Provide Bill to Customer**
7. **Stock Automatically Updated**

---

### Workflow 4: Month-End Closing

**Last day of month:**

1. **Physical Stock Count**
   - Count all medicines in store
   - Enter discrepancies as adjustments

2. **Reconciliation**
   - System stock vs. Physical stock
   - Investigate differences

3. **Generate Reports**
   - Sales summary
   - Stock statement
   - GST report
   - Supplier payment summary

4. **Payments**
   - Pay outstanding supplier bills
   - Collect outstanding customer dues

5. **Backup Data**
   - System auto-backs up
   - Store on secure location (recommended)

---

## Tips & Best Practices

### 1. Data Entry

✅ **Do:**
- Use consistent medicine names
- Keep supplier information updated
- Enter batch details accurately
- Verify prices before saving

❌ **Don't:**
- Create duplicate medicines with similar names
- Leave expiry dates blank
- Skip audit trail entries
- Process sales manually if POS available

### 2. Stock Management

✅ **Do:**
- Set realistic reorder levels based on sales velocity
- Review slow-moving items monthly
- Maintain proper batch records
- Conduct physical stock counts quarterly

❌ **Don't:**
- Ignore low stock alerts
- Sell medicines beyond expiry date
- Process large adjustments without verification
- Keep medicines improperly stored

### 3. Compliance & Regulations

✅ **Do:**
- Follow FIFO (First-In-First-Out) for batch selection
- Maintain schedule drug compliance
- Keep valid prescriptions for schedule drugs
- Generate audit trails for all transactions
- File GST returns on time

❌ **Don't:**
- Sell schedule H/X drugs without prescription
- Manipulate stock records
- Skip GST calculations
- Delete transaction records

### 4. Security & Access

✅ **Do:**
- Change password regularly (every 30 days)
- Enable two-factor authentication
- Log out when leaving computer
- Use strong passwords
- Report any suspicious activity

❌ **Don't:**
- Share login credentials
- Write password on sticky notes
- Use simple passwords (123456, password)
- Leave device unattended while logged in

### 5. Regular Maintenance

✅ **Do:**
- Review reports monthly
- Clean up old data (archive if needed)
- Update supplier information regularly
- Reconcile accounts monthly
- Test backup restoration

❌ **Don't:**
- Ignore system updates
- Let discrepancies pile up
- Postpone reconciliation
- Work without backups

---

## Troubleshooting

### Issue 1: Cannot Access the Application

**Problem:** Browser shows "Cannot reach server"

**Solutions:**
1. Check internet connection
   - Ping google.com from command line
   - Restart router if needed

2. Check if application is running
   - Server might be down
   - Contact IT support

3. Try different browser
   - Clear cookies: Ctrl+Shift+Delete
   - Try incognito/private mode

4. Check firewall
   - Ensure port 4000 (frontend) and 8000 (backend) are allowed

### Issue 2: Slow Performance

**Problem:** Application is slow/freezing

**Solutions:**
1. Check internet speed
   - Minimum 4 Mbps required
   - Contact ISP if slower

2. Close unnecessary tabs
   - Reduces browser memory usage

3. Clear browser cache
   - Settings → Clear Browsing Data

4. Reduce search filters
   - Searching large datasets is slow
   - Use date range limits

5. Contact support if persists

### Issue 3: Barcode Scanner Not Working

**Problem:** Barcode scanner doesn't scan items

**Solutions:**
1. Test scanner separately
   - Scan on notepad to verify
   - Check USB connection

2. Check scanner mode
   - Set to USB/Keyboard mode
   - Not serial/PS2

3. In POS, ensure focus
   - Click in medicine search box
   - Scan should add items automatically

4. Update scanner driver
   - Download from manufacturer website

### Issue 4: Incorrect Stock Numbers

**Problem:** System shows different stock than physical

**Solutions:**
1. Conduct physical count
   - Count all items manually
   - Note quantities

2. Enter adjustment
   - Inventory → Adjustment
   - Report difference with reason

3. Investigate cause
   - Check if bills are correct
   - Verify no unauthorized sales

4. Review audit trail
   - See all stock movements for that medicine

### Issue 5: Cannot Process Sale

**Problem:** Error while creating bill/processing payment

**Solutions:**
1. Refresh page (F5)
2. Try different medicine
3. Clear browser cache
4. Try another browser
5. Contact support with error message

### Issue 6: Forgotten Password

**Problem:** Cannot log in

**Solution:**
1. Click **"Forgot Password"** on login page
2. Enter your **email/username**
3. Check email for reset link
4. Click link and set new password
5. Log in with new password
6. Change password after first login

### Issue 7: Permission Denied Error

**Problem:** "You don't have permission" error

**Solutions:**
1. Verify your user role
   - Admin sees all features
   - Other roles have restrictions
   
2. Contact system administrator
   - Ask for required permission
   - Provide your use case

3. Log out and log back in
   - Permissions may need refresh

---

## Support & Contact

### Getting Help

**For Technical Issues:**
1. Check this guide's Troubleshooting section
2. Email: support@pharmacyerp.com
3. Call: +91-XXXX-XXXX-XX
4. Chat: In-app chat (if available)

**Information to Provide When Reporting Issues:**

Include:
- Browser name and version
- Operating system
- Screenshot of error (if applicable)
- Steps to reproduce the problem
- When it started happening
- Any recent changes you made

**Response Times:**
- Critical issues: Within 2 hours
- High priority: Within 8 hours
- Normal: Within 24 hours

---

### Frequently Asked Questions (FAQ)

**Q1: How often should I backup my data?**
A: System auto-backups daily. We recommend weekly manual backups to external storage.

**Q2: Can I export data to Excel?**
A: Yes, most reports have "Export to Excel" option. Navigate to Reports section.

**Q3: What if I accidentally delete a medicine?**
A: Contact your administrator. They can restore from backup. Keep a record of what was deleted.

**Q4: How many user accounts can I create?**
A: Depends on your license. Contact your provider for details.

**Q5: Can I integrate with my existing accounting software?**
A: Yes, we provide API documentation. Ask support for integration details.

**Q6: How is GST calculated?**
A: System uses HSN code and tax rate specified. SGST+CGST for intra-state, IGST for inter-state.

**Q7: Can customers access their purchase history?**
A: Depends on configuration. Contact admin if you want to enable this.

**Q8: What happens to data if I exceed subscription?**
A: Read-only access. Contact provider to upgrade or manage subscription.

**Q9: Is my data secure?**
A: Yes. We use encryption, secure authentication, and regular backups. All transactions are logged.

**Q10: Can I use this on mobile?**
A: Yes. The system is responsive and works on tablets and phones. Login same as desktop.

---

### Video Tutorials

For visual learning, we provide video tutorials:
1. **Getting Started** (5 min)
2. **Processing Your First Sale** (8 min)
3. **Managing Stock** (10 min)
4. **Creating Purchase Orders** (7 min)
5. **Generating Reports** (6 min)

Videos available at: [Link to video channel]

---

### Training & Onboarding

**New users can:**
1. Contact support for personalized training
2. Attend group training sessions (schedule provided)
3. Request on-site training (paid service)
4. Schedule 1-on-1 training call with expert

---

## Important Notes

### Compliance & Legal

- **GST Compliance**: System calculates GST per current rates. You're responsible for correct HSN codes.
- **Schedule Drugs**: Maintain proper documentation for H and X schedule drugs.
- **Data Privacy**: Your data is confidential and encrypted.
- **Audit Trail**: All transactions are logged for regulatory compliance.

### Regular Updates

- System receives regular updates for:
  - Bug fixes
  - New features
  - Security patches
  - GST/Tax rate updates
  
- Updates typically deployed monthly
- Scheduled maintenance windows communicated in advance

### Support for Different Roles

**Pharmacist**: How to process sales and manage stock
**Store Manager**: Reports, approvals, and inventory oversight
**Admin**: User management, system configuration
**Cashier**: Point of Sale (POS) training

---

## Document Version & Support

**Document Version**: 1.0
**Last Updated**: May 2026
**System Version**: 1.0.0

For the latest updates to this guide, visit: [Link to documentation site]

---

**Thank you for using the Pharmacy Inventory Management System!**

For more information or assistance, contact: support@pharmacyerp.com

**Happy managing! 💊**
