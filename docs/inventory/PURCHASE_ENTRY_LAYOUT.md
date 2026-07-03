# Purchase Entry Module - Page Structure & Layout

## Visual Layout Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PURCHASE ENTRY PAGE                             │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┬──────────────────┐
│                                                      │                  │
│  ┌─ HEADER SECTION ─────────────────────────────┐  │  PRODUCT DETAILS │
│  │ Title: Purchase Entry                        │  │  (If row selected)
│  │ Invoice Number: PI-1234567890                │  │                  │
│  │ Purchase Date: [2026-06-08]                  │  │  • Medicine Name │
│  │ Supplier Invoice #: [________]               │  │  • Generic Name  │
│  │ Supplier Invoice Date: [__________]          │  │  • Company       │
│  │                                               │  │  • Category      │
│  └───────────────────────────────────────────────┘  │  • HSN Code      │
│                                                      │  • Batch #       │
│  ┌─ SUPPLIER SECTION ────────────────────────────┐  │  • Expiry Date   │
│  │ Supplier Name: [Search...▼]                  │  │  • Barcode       │
│  │ (Shows details when selected)                │  │                  │
│  │ • GST Number: 27AABCU9203R1Z5                │  │  Pricing:        │
│  │ • Phone: +91 98765 43210                     │  │  • Purchase Rate │
│  │ • Contact: John Doe                          │  │  • MRP           │
│  │ • Address: Mumbai, India                     │  │  • Selling Rate  │
│  │                                               │  │  • Profit Margin │
│  └───────────────────────────────────────────────┘  │                  │
│                                                      │  Tax:            │
│  ┌─ MEDICINE GRID (SCROLLABLE) ──────────────┐     │  • GST Rate      │
│  │ #│Product│Generic│Company│Batch│Exp │Qty │Disc │                  │
│  ├──┼───────┼───────┼───────┼─────┼────┼────┼─────┤  ├─ SUMMARY ─────┤
│  │1 │Paraca │Paraca │GSK    │B123 │... │100 │5%  │  │ Total Items: 2 │
│  │2 │Aspirin│Aspirin│Bayer  │B456 │... │50  │0%  │  │ Total Qty: 150 │
│  │3 │Ibuprof│Ibuprof│Pfizer │B789 │... │75  │10% │  │ Free Qty: 0    │
│  │  │[+ Add]│       │       │     │    │    │    │  │                │
│  │                                               │  │ Subtotal: ₹500 │
│  └───────────────────────────────────────────────┘  │ Line Disc: -₹50│
│                                                      │ Taxable: ₹450  │
│  ┌─ ADDITIONAL INFO ─────────────────────────────┐  │ GST Total: ₹54 │
│  │ Challan #: [_____________]                   │  │                │
│  │ Warehouse: [_____________]                   │  │ Paid Amount: 0 │
│  │ Receiving Staff: [_____________]             │  │ Add Disc: 0    │
│  │ Purchase Type: [Regular▼]                    │  ├────────────────┤
│  │ Payment Mode: [Cash▼]                        │  │  NET AMOUNT    │
│  │ Transport: [Textarea...]                     │  │  ₹504          │
│  │ Notes: [Textarea...]                         │  │ Due: ₹504      │
│  │                                               │  │                │
│  └───────────────────────────────────────────────┘  │ Status: PENDING│
│                                                      ├────────────────┤
│                           ┌─────────────────────┐   │ [Save Purchase]│
│                           │ [Save Purchase]     │   │ [Save & Print] │
│                           │ [Save & Print]      │   │ [Save Draft]   │
│                           │ [Save Draft]        │   │ [Cancel]       │
│                           │ [Cancel]            │   │                │
│                           └─────────────────────┘   │                │
│                                                      │                │
│                                                      │                │
└──────────────────────────────────────────────────────┴──────────────────┘
```

---

## Component Tree Structure

```
PurchaseEntryPage (Main Container)
│
├── Error/Success Messages
│   ├── Error Alert (if error)
│   └── Success Alert (if saved)
│
├── LEFT COLUMN (lg:col-span-2)
│   ├── PurchaseHeader
│   │   ├── Title & Invoice Display
│   │   ├── Purchase Date Input
│   │   ├── Supplier Invoice Number Input
│   │   ├── Supplier Invoice Date Input
│   │   └── Created By (Read-only)
│   │
│   ├── SupplierSection
│   │   ├── Searchable Dropdown
│   │   │   └── Real-time Filter
│   │   ├── Auto-filled Fields (Read-only)
│   │   │   ├── Supplier Code
│   │   │   ├── GST Number
│   │   │   ├── Phone
│   │   │   ├── Contact Person
│   │   │   └── Address
│   │   └── Helpful Tip (if no supplier)
│   │
│   ├── MedicineGrid Section
│   │   ├── Header (Title + Add Item Button)
│   │   ├── Grid Table
│   │   │   ├── Header Row
│   │   │   ├── Data Rows (Editable)
│   │   │   │   ├── Row Number
│   │   │   │   ├── Product Dropdown
│   │   │   │   ├── Generic (Read-only)
│   │   │   │   ├── Company (Read-only)
│   │   │   │   ├── Batch (Editable)
│   │   │   │   ├── Expiry Date (Editable)
│   │   │   │   ├── Quantity (Editable)
│   │   │   │   ├── Rate (Editable)
│   │   │   │   ├── Discount % (Editable)
│   │   │   │   ├── GST % (Editable)
│   │   │   │   ├── Amount (Calculated)
│   │   │   │   └── Delete Button
│   │   │   │
│   │   │   ├── Expanded Row (on selection)
│   │   │   │   ├── MRP (Editable)
│   │   │   │   ├── Selling Rate (Editable)
│   │   │   │   └── Barcode (Read-only)
│   │   │   │
│   │   │   └── Summary Row
│   │   │       ├── Item Count
│   │   │       └── Total Quantity
│   │   │
│   │   └── Empty State (if no items)
│   │
│   └── AdditionalInfo
│       ├── Challan Number (Optional)
│       ├── Warehouse (Optional)
│       ├── Receiving Staff (Optional)
│       ├── Purchase Type (Dropdown)
│       ├── Payment Mode (Dropdown)
│       ├── Transport Details (Textarea)
│       └── Notes (Textarea)
│
└── RIGHT COLUMN (lg:col-span-1)
    ├── ProductDetailsPanel (Conditional)
    │   ├── Medicine Name
    │   ├── Generic Name
    │   ├── Company
    │   ├── Category
    │   ├── HSN Code
    │   ├── Batch Number
    │   ├── Expiry Date
    │   ├── Barcode
    │   ├── Pricing Section
    │   │   ├── Purchase Rate
    │   │   ├── MRP
    │   │   ├── Selling Rate
    │   │   └── Profit Margin %
    │   └── Tax Section
    │       ├── GST Rate
    │       └── Discount %
    │
    ├── PurchaseSummaryPanel (Sticky)
    │   ├── Summary Section
    │   │   ├── Total Items
    │   │   ├── Total Quantity
    │   │   └── Free Quantity (if any)
    │   ├── Amount Section
    │   │   ├── Subtotal
    │   │   ├── Line Discounts
    │   │   ├── Header Discount
    │   │   ├── Taxable Amount
    │   │   ├── GST Total
    │   │   └── Round Off
    │   ├── Payment Section
    │   │   ├── Paid Amount (Editable)
    │   │   └── Additional Discount (Editable)
    │   ├── Net Amount (Prominent Display)
    │   │   └── Due Amount
    │   └── Payment Status
    │       ├── FULLY PAID (Green)
    │       └── PENDING (Orange)
    │
    └── Action Buttons
        ├── Save Purchase
        ├── Save & Print
        ├── Save Draft
        └── Cancel
```

---

## Data Flow Diagram

```
┌─────────────────┐
│  User Input     │
│  (Typing/Click) │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  Event Handler              │
│  (onChange, onClick, etc.)  │
└────────┬────────────────────┘
         │
         ▼
┌──────────────────────────┐
│  State Update            │
│  setFormData({...})      │
└────────┬─────────────────┘
         │
         ▼
┌────────────────────────────────┐
│  Calculation (useCallback)     │
│  totals() recalculates          │
│  All 8 amount fields update    │
└────────┬───────────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Component Re-render     │
│  All affected components │
│  update their UI         │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  User Sees Updates       │
│  (Instant feedback)      │
└──────────────────────────┘
```

---

## Grid Column Details

```
┌─────┬──────────┬─────────┬───────┬──────┬────────┬─────┬──────┬────┬────┬────────┬─────┐
│  #  │ Product  │ Generic │ Corp  │Batch │ Expiry │ Qty │ Rate │Dis%│GST%│Amount  │Del  │
├─────┼──────────┼─────────┼───────┼──────┼────────┼─────┼──────┼────┼────┼────────┼─────┤
│  1  │ [Select] │ R/O     │ R/O   │[____]│[_____] │[__] │[____]│[__]│[__]│₹[____] │[X]  │
│  2  │ [Select] │ R/O     │ R/O   │[____]│[_____] │[__] │[____]│[__]│[__]│₹[____] │[X]  │
│ ... │   ...    │  ...    │ ...   │ ...  │  ...   │ ... │ ...  │... │... │  ...   │ ... │
└─────┴──────────┴─────────┴───────┴──────┴────────┴─────┴──────┴────┴────┴────────┴─────┘

Expanded Row (On Selection):
┌─────────────────────────────────────────────────────────────────────┐
│ MRP: [_____]  │ Selling Rate: [_____]  │ Barcode: [____________] R/O│
└─────────────────────────────────────────────────────────────────────┘

Legend:
  R/O = Read-Only (Auto-filled)
  [__] = Editable field
  [X] = Delete button
```

---

## Responsive Breakpoints

### Desktop (lg: 1024px+)
```
┌─────────────────────────────────────┬─────────────┐
│  Main Content (col-span-2)          │  Sidebar    │
│  • Header                           │  (col-span) │
│  • Supplier                         │             │
│  • Grid                             │  Details    │
│  • Additional Info                  │  +          │
│                                     │  Summary    │
│                                     │  +          │
│                                     │  Actions    │
└─────────────────────────────────────┴─────────────┘
```

### Tablet (md: 768px)
```
┌──────────────────────────┬──────────────┐
│  Main Content            │  Sidebar     │
│  (Slightly narrower)     │  (Narrower)  │
│                          │              │
│                          │              │
└──────────────────────────┴──────────────┘
```

### Mobile (< 768px)
```
┌──────────────────────┐
│  Header              │
├──────────────────────┤
│  Supplier            │
├──────────────────────┤
│  Grid                │
│  (Horizontally       │
│   scrollable)        │
├──────────────────────┤
│  Additional Info     │
├──────────────────────┤
│  Details Panel       │
│  (if row selected)   │
├──────────────────────┤
│  Summary Panel       │
├──────────────────────┤
│  Action Buttons      │
└──────────────────────┘
```

---

## State Object Structure

```typescript
formData = {
  invoice_number: "PI-1234567890",
  purchase_date: "2026-06-08",
  supplier_id: "507f1f77bcf86cd799439011",
  supplier_name: "Supplier Name (Optional)",
  supplier_invoice_number: "INV-123",
  supplier_invoice_date: "2026-06-08",
  purchase_type: "regular",
  payment_mode: "cash",
  challan_number: "CHK-123",
  transport_details: "Vehicle details...",
  notes: "Special instructions...",
  warehouse_id: "WH-001",
  receiving_staff: "John Doe",
  
  items: [
    {
      medicine_id: "507f1f77bcf86cd799439012",
      medicine_name: "Paracetamol",
      generic_name: "Paracetamol",
      company: "GSK",
      batch_number: "B123456",
      expiry_date: "2027-06-08",
      quantity: 100,
      free_quantity: 0,
      purchase_price: 5.50,
      discount_percentage: 5,
      gst_percentage: 12,
      mrp: 10.00,
      selling_price: 9.00,
      barcode: "5012345678901",
      line_total: 604.77  // Calculated
    },
    // More items...
  ],
  
  discount: 0,      // Header-level discount
  paid_amount: 0,   // Amount paid
}
```

---

## Calculation Examples

### Example 1: Simple Item
```
Inputs:
  Qty = 100
  Purchase Price = ₹5.00
  Discount% = 0
  GST% = 12

Calculations:
  Line Subtotal = 100 × 5.00 = ₹500
  Line Discount = 500 × 0% = ₹0
  Taxable Amount = 500 - 0 = ₹500
  GST Amount = 500 × 12% = ₹60
  Line Total = 500 + 60 = ₹560
```

### Example 2: With Discount
```
Inputs:
  Qty = 50
  Purchase Price = ₹10.00
  Discount% = 10
  GST% = 12

Calculations:
  Line Subtotal = 50 × 10.00 = ₹500
  Line Discount = 500 × 10% = ₹50
  Taxable Amount = 500 - 50 = ₹450
  GST Amount = 450 × 12% = ₹54
  Line Total = 450 + 54 = ₹504
```

### Example 3: Multiple Items with Header Discount
```
Item 1:
  Line Subtotal = ₹500, GST = ₹60, Line Total = ₹560

Item 2:
  Line Subtotal = ₹300, GST = ₹36, Line Total = ₹336

Item 3:
  Line Subtotal = ₹200, GST = ₹24, Line Total = ₹224

Summary:
  Total Subtotal = 500 + 300 + 200 = ₹1,000
  Total GST = 60 + 36 + 24 = ₹120
  Subtotal + GST = 1,000 + 120 = ₹1,120
  Header Discount = ₹50
  Net Amount = 1,120 - 50 = ₹1,070
  
  If Paid = ₹1,000
  Due Amount = 1,070 - 1,000 = ₹70
```

---

## Color Scheme

```
Primary Colors:
  Emerald (Actions):        #10b981
    Light: #ecfdf5
    Dark: #065f46

Secondary Colors:
  Slate (Text/Backgrounds): #64748b
    Light: #f1f5f9
    Dark: #0f172a

Status Colors:
  Success (Green):          #10b981
  Error (Red):              #ef4444
  Warning (Orange):         #f97316
  Info (Blue):              #3b82f6

Text Colors:
  Primary (900):            #0f172a
  Secondary (600):          #475569
  Muted (500):              #64748b
```

---

## Form Validation Rules

```
Before Save:
┌─────────────────────────────────────┐
│ Is Supplier Selected?               │
│ ├─ NO → "Please select a supplier"  │
│ └─ YES → Continue                   │
│                                      │
│ Are there Items?                    │
│ ├─ NO → "Add at least one medicine" │
│ └─ YES → Continue                   │
│                                      │
│ For Each Item:                      │
│ ├─ Is Medicine Selected?            │
│ │  └─ NO → "Row X: Select medicine" │
│ ├─ Is Batch Number Filled?          │
│ │  └─ NO → "Row X: Enter batch"     │
│ ├─ Is Quantity > 0?                 │
│ │  └─ NO → "Row X: Qty must be > 0" │
│ └─ Is Purchase Price > 0?           │
│    └─ NO → "Row X: Enter price"     │
│                                      │
│ All Valid? → Save to API            │
└─────────────────────────────────────┘
```

---

## User Interaction Flow

```
1. Page Loads
   └─ Suppliers & medicines fetched from API

2. User Selects Supplier
   └─ Details auto-populate

3. User Adds First Item
   └─ New row appears

4. User Selects Medicine
   └─ Details auto-fill (generic, company, GST%)

5. User Enters Batch & Dates
   └─ Row data updates

6. User Enters Qty & Rate
   └─ Amount calculates instantly
   └─ Summary updates

7. User Adjusts Discounts/Tax
   └─ Amount recalculates
   └─ Summary updates

8. User Clicks Row
   └─ Details panel shows
   └─ Expandable row shows

9. User Adds More Items
   └─ Repeat 3-8

10. User Reviews Summary
    └─ Checks calculations
    └─ Enters paid amount
    └─ Sees due amount

11. User Clicks Save
    └─ Validation runs
    └─ If valid → API call
    └─ Success message
    └─ Form resets
```

---

This visual guide provides a complete understanding of:
- ✓ Page layout and structure
- ✓ Component hierarchy
- ✓ Data flow
- ✓ Grid columns
- ✓ Responsive design
- ✓ Color scheme
- ✓ Validation rules
- ✓ User interaction flow

Use this alongside the other documentation for complete implementation understanding.
