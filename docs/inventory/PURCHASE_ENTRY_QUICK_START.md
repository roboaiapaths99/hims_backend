# Purchase Entry Module - Quick Start Guide

## Getting Started

### Prerequisites
- Node.js 16+ installed
- Backend running (Uvicorn server)
- Database (MongoDB) running
- All dependencies installed

### Step 1: Start the Application

#### Terminal 1 - Backend
```powershell
cd backend
..\scripts\start-backend.ps1
# Or manually:
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Terminal 2 - Frontend
```powershell
cd frontend
npm run dev
# Application will be at http://localhost:4000
```

### Step 2: Navigate to Purchase Entry
1. Login with your credentials
2. Click "Purchase" in the left sidebar (under "Purchases & Sales" section)
3. Or navigate directly to `http://localhost:4000/purchase`

## Using the Purchase Entry Page

### Basic Workflow

#### 1. **Fill Invoice Header**
   - **Purchase Date:** Select today's date (auto-filled)
   - **Supplier Invoice Number:** Enter the invoice number from supplier
   - **Supplier Invoice Date:** Enter the date from supplier invoice
   - These fields are optional but recommended

#### 2. **Select Supplier**
   - Click "Supplier Name" field
   - Start typing to search suppliers
   - Click to select
   - Supplier details auto-fill:
     - GST Number
     - Phone
     - Contact Person
     - Address

#### 3. **Add Medicines**
   - Click **"+ Add Item"** button
   - A new row appears in the grid
   - Fill in order:

   **Step 1:** Select Medicine
   ```
   1. Click "Product Name" dropdown
   2. Type medicine name to search
   3. Click to select
   4. Auto-fills: Generic Name, Company, Barcode, GST%
   ```

   **Step 2:** Enter Batch Details
   ```
   1. Batch Number → Enter from supplier invoice
   2. Expiry Date → Pick date from calendar
   ```

   **Step 3:** Enter Quantity & Price
   ```
   1. Qty → Number of units
   2. Rate → Purchase price per unit
   3. Amount auto-calculates!
   ```

   **Step 4:** Optional Fields (Click to Expand Row)
   ```
   1. MRP → Max Retail Price
   2. Selling Rate → Your selling price
   3. Barcode → Auto-filled from medicine master
   ```

#### 4. **Adjust Discounts & Tax**
   - **Disc%:** Line-level discount percentage
   - **GST%:** GST rate (auto-filled from medicine master)
   - All amounts recalculate automatically

#### 5. **Review Summary Panel (Right Side)**
   - Check totals in real-time
   - See GST breakdown
   - Enter **Paid Amount** (if paying now)
   - Enter **Additional Discount** (if any)
   - View **Net Amount** (final total)
   - Check payment status

#### 6. **Add Optional Details**
   - **Challan Number:** From supplier
   - **Warehouse:** Where stock will be stored
   - **Receiving Staff:** Who received the goods
   - **Purchase Type:** Regular/Return/Credit/Consignment
   - **Payment Mode:** Cash/Cheque/Bank/UPI/Credit
   - **Transport Details:** Vehicle, agency, delivery date
   - **Notes:** Any special instructions

#### 7. **Save Purchase**
   - Click **"Save Purchase"** to complete
   - Or **"Save & Print"** to print invoice
   - Or **"Save Draft"** to save for later
   - Success message appears

### Keyboard Shortcuts (Recommended)

| Action | Shortcut |
|--------|----------|
| Move to next field | `Tab` |
| Move to previous field | `Shift + Tab` |
| Select from dropdown | `Enter` |
| Delete item row | Click trash icon |
| Clear selection | `Escape` |

### Pro Tips

1. **Quick Data Entry**
   - Use Tab to move between fields rapidly
   - Auto-fill reduces typing significantly
   - Calculations are instant

2. **Batch Entry**
   - Add all items first
   - Then review total in summary
   - Discount & payment info in summary panel

3. **Editing**
   - Click row to view all details in right panel
   - Edit any field directly in grid
   - All calculations update instantly

4. **Verification**
   - Always verify Supplier is correct (auto-fills details)
   - Check Medicine selection (auto-fills generics & tax)
   - Review Summary totals before saving
   - Check payment status (Fully Paid / Pending)

## Common Scenarios

### Scenario 1: Regular Purchase with Multiple Items

```
1. Click "Purchase" in menu
2. Date auto-filled (today)
3. Select Supplier → Details auto-fill
4. Click "+ Add Item"
5. Select Medicine #1 → Details auto-fill
6. Enter: Batch, Expiry, Qty, Rate
7. Click "+ Add Item" again
8. Select Medicine #2 → Details auto-fill
9. Enter: Batch, Expiry, Qty, Rate
10. Review Summary Panel
11. Enter Paid Amount
12. Click "Save Purchase"
13. ✓ Success! Invoice saved
```

### Scenario 2: Purchase with Header-Level Discount

```
1. Add all medicines to grid
2. Review Summary Panel on right
3. In Summary → Enter "Additional Discount" amount
4. Net Amount updates automatically
5. Check payment status
6. Save Purchase
```

### Scenario 3: Credit Purchase (Payment Later)

```
1. Add medicines to grid
2. Summary shows Net Amount
3. Leave "Paid Amount" as 0
4. Summary shows: "PENDING ₹XXXX"
5. Enter Payment Mode: "Credit"
6. Save Purchase
7. Supplier due balance updates automatically
```

### Scenario 4: Purchase with Expiry Soon

```
1. Add medicine
2. Choose expiry date (e.g., 3 months from now)
3. Grid shows expiry date
4. Right panel shows expiry in Product Details
5. Save normally
```

## Understanding the Summary Panel

The **right-side sticky panel** shows all calculations:

```
SUMMARY
────────────────────
Total Items:        3
Total Quantity:    250
────────────────────

AMOUNTS
Subtotal:       ₹2,500
Line Discount:   -₹250
Taxable Amount: ₹2,250
GST Total:       +₹270
────────────────────

Paid Amount:        ₹0
Additional Disc:    ₹0

╔════════════════════╗
║  NET AMOUNT        ║
║  ₹2,520            ║
║ Due: ₹2,520        ║
╚════════════════════╝

Status: PENDING
```

**Color Indicators:**
- 🟢 **Green:** GST amounts added, Fully paid status
- 🟠 **Orange:** Discounts applied, Pending amount
- 🔴 **Red:** Error messages

## Field Descriptions

### Header Section
| Field | Required | Format | Example |
|-------|----------|--------|---------|
| Purchase Date | No | YYYY-MM-DD | 2026-06-08 |
| Supplier Invoice # | No | Text | INV-12345 |
| Supplier Invoice Date | No | YYYY-MM-DD | 2026-06-08 |

### Supplier Section
| Field | Required | Source | Notes |
|-------|----------|--------|-------|
| Supplier Name | **YES** | Dropdown | Auto-populates details |
| GST Number | N/A | Auto-fill | Read-only |
| Phone | N/A | Auto-fill | Read-only |
| Contact Person | N/A | Auto-fill | Read-only |

### Medicine Grid
| Field | Required | Type | Notes |
|-------|----------|------|-------|
| Product Name | **YES** | Dropdown | Must select from list |
| Batch Number | **YES** | Text | From supplier invoice |
| Expiry Date | **YES** | Date | Future date |
| Quantity | **YES** | Number | Positive integer |
| Purchase Rate | **YES** | Currency | Price per unit |
| Disc% | No | Number | 0-100, default 0 |
| GST% | No | Number | Auto-filled, editable |

### Additional Fields (Expandable)
| Field | Type | Notes |
|-------|------|-------|
| MRP | Currency | Max Retail Price |
| Selling Rate | Currency | Your selling price |
| Barcode | Text | Auto-filled, read-only |

### Additional Info Section
| Field | Type | Options |
|-------|------|---------|
| Challan # | Text | From supplier |
| Warehouse | Text | Storage location |
| Receiving Staff | Text | Staff name |
| Purchase Type | Dropdown | Regular/Return/Credit/Consignment |
| Payment Mode | Dropdown | Cash/Cheque/Bank/UPI/Credit |
| Transport Details | Text area | Vehicle, agency info |
| Notes | Text area | Special instructions |

## Troubleshooting

### Issue: "Please select a supplier"
**Solution:** 
- Click Supplier Name field
- Type to search for supplier
- Select one from the list

### Issue: Supplier details not showing
**Solution:**
- Ensure supplier is selected (not just typed)
- Check if suppliers are loaded from database
- Try selecting again

### Issue: Medicine not populating details
**Solution:**
- Ensure medicine is selected from dropdown
- Don't type manually - select from list
- Check if medicines are loaded

### Issue: Calculations look wrong
**Solution:**
- Check all line item amounts
- Verify GST rates
- Check quantity values
- Verify purchase rates

### Issue: "Invalid purchase ID" when saving
**Solution:**
- Ensure all required fields are filled
- Check that supplier is properly selected
- Verify at least one valid medicine item is added
- Check browser console for detailed error

### Issue: Page takes too long to load
**Solution:**
- Check if backend API is running
- Verify database connection
- Check browser console for errors
- Refresh page

## Getting Help

1. **Check Documentation:** See `PURCHASE_ENTRY_DOCUMENTATION.md` for complete details
2. **Look at Code:** Check `frontend/components/purchase/` for implementation details
3. **Backend Logs:** Check terminal running backend for error messages
4. **Browser Console:** Press F12 → Console for JavaScript errors

## Data Safety

- ✓ Supplier selected must exist in database
- ✓ Medicines selected must exist in database
- ✓ Invoice numbers must be unique
- ✓ All required fields validated before save
- ✓ Complete audit trail maintained
- ✓ Stock ledger updated automatically

## Performance Notes

- Page loads 500+ medicines and suppliers
- Real-time calculations (no lag)
- Smooth scrolling and interactions
- Professional animation transitions
- Responsive on all screen sizes

## Next Steps

1. ✓ Load the page
2. ✓ Try adding a practice purchase
3. ✓ Review summary calculations
4. ✓ Save and verify in database
5. ✓ Check Purchase History page
6. ✓ Verify stock levels updated

Congratulations! You now have a professional-grade Purchase Entry system. 🎉
