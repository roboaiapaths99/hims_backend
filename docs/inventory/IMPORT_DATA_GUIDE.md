# Pharmacy Data Import Feature

## Overview
The Import Data feature allows pharmacists to bulk import medicine inventory data from Excel or CSV files. This eliminates manual entry and ensures accurate, efficient inventory management.

## Quick Start

### Step 1: Download the Template
1. Go to **Inventory Management** → **Import Data**
2. Click on the **Template Guide** tab
3. Click **Download Excel Template**
4. The template file will be saved as `pharmacy_import_template.xlsx`

### Step 2: Fill in Your Data
Open the downloaded Excel file and fill in the data with these guidelines:

#### Required Columns (Must be filled):
- **Medicine Name**: Full name of the medicine (e.g., "Paracetamol 500mg")
- **Generic Name**: Generic/INN name (e.g., "Paracetamol")
- **Brand Name**: Brand name of the product
- **Category**: Medicine category or therapeutic group (e.g., "Antipyretic", "Antibiotic")
- **Current Stock**: Current quantity in stock (numbers only, no commas)
- **MRP**: Maximum Retail Price in ₹ (e.g., 50.00)
- **Purchase Rate**: Cost price in ₹ (e.g., 25.00)
- **Manufacturer**: Manufacturer name (e.g., "GSK", "Abbott")

#### Optional Columns (Can be left blank):
- **HSN Code**: 8-digit HSN/SAC code for GST (e.g., "30041090")
- **GST Percentage**: GST rate 0-28% (e.g., 5)
- **Unit Type**: Unit of measurement (PCS, ML, MG, STRIP, etc.) - defaults to "PCS"
- **Minimum Stock**: Minimum stock level for alerts (e.g., 20)
- **Reorder Quantity**: Quantity to order when stock is low (e.g., 50)
- **Batch Number**: Batch/Lot number (e.g., "B001")
- **Expiry Date**: Expiry date in YYYY-MM-DD format (e.g., "2025-12-31")
- **Barcode**: Product barcode (e.g., "1234567890")
- **Rack Number**: Storage location/rack number (e.g., "A1", "Shelf-2")

### Step 3: Format Your Data Correctly

#### Number Formatting:
- **DO**: Use `100` or `100.50` for prices and quantities
- **DON'T**: Use `100,000` or `100.50 ₹`
- Negative stock values are allowed (for correction during import)

#### Date Formatting:
- **Accepted formats**: 
  - YYYY-MM-DD (e.g., 2025-12-31)
  - DD-MM-YYYY (e.g., 31-12-2025)
  - MM/DD/YYYY (e.g., 12/31/2025)
  - DD/MM/YYYY (e.g., 31/12/2025)

#### Text Fields:
- No special characters that might break the CSV
- Keep names under 200 characters
- Avoid leading/trailing spaces (they will be trimmed)

### Step 4: Upload and Import

1. Go to **Inventory Management** → **Import Data**
2. Click on the **Upload & Import** tab
3. Click the upload area and select your Excel/CSV file
4. Click **Validate & Preview**
5. Review the validation report:
   - ✓ Valid records will be shown
   - ⚠ Warnings highlight potential issues (non-blocking)
   - ✗ Errors must be fixed before import
6. If there are no errors, click **Confirm & Import**
7. Wait for the import to complete

## Data Validation Rules

### Validation Checks:
- ✓ All required fields are filled
- ✓ Stock quantities are valid numbers
- ✓ MRP and Purchase Rate > 0
- ✓ GST percentage is between 0-28%
- ✓ Dates are in valid format
- ⚠ Negative stock values trigger a warning
- ⚠ Missing batch-wise expiry data generates a warning

### Common Errors and Fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| "Medicine name is required" | Empty medicine name cell | Fill in the medicine name |
| "Category is required" | Empty category cell | Specify a category |
| "MRP must be greater than 0" | Zero or negative MRP | Enter a valid MRP value |
| "Purchase rate must be greater than 0" | Zero or negative purchase rate | Enter a valid cost price |
| "Invalid expiry date format" | Date not in expected format | Use YYYY-MM-DD format |
| "Missing required columns" | Column headers don't match | Don't modify column headers in template |

## Import Flow

```
1. Select File
   ↓
2. Validate Data
   ├─ Check Required Fields
   ├─ Validate Data Types
   ├─ Check Business Rules
   └─ Generate Sample Preview
   ↓
3. Review Validation Results
   ├─ View Valid Records Count
   ├─ View Warnings (if any)
   ├─ View Errors (if any)
   └─ View Sample Data
   ↓
4. Confirm & Import (if no errors)
   ├─ Check for Duplicates
   ├─ Create or Update Records
   ├─ Update Stock Levels
   └─ Log Import Activity
   ↓
5. View Results
   ├─ Import Success Count
   ├─ Import History
   └─ Updated Inventory
```

## Features

### Preview Before Import
- See sample rows from your file before import
- Review validation results and errors
- Preview exactly what will be imported

### Duplicate Handling
- If a medicine with the same name and category exists, it will be **updated**
- Otherwise, a **new record** is created
- Batch numbers help identify different batches of the same medicine

### Batch Import Limits
- Maximum records per file: 10,000
- Recommended batch size: 1,000-2,000 for optimal performance

### Import History
- View all past imports
- Track import dates and success rates
- Monitor import activity

## Data Updates After Import

### Automatic Updates:
After successful import, the following pages will be updated automatically:

1. **Stock Management** - Shows all imported stock levels
2. **Low Stock Alerts** - Flags items below minimum stock
3. **Expiry Tracking** - Displays expiry information if provided
4. **Reports & Analytics** - Updates all inventory metrics
5. **Dashboard** - Refreshes all statistics
6. **Stock Transfers** - Available for stock balancing
7. **Suppliers** - Shows supplier information from imports

### What Gets Updated:
- ✓ Medicine master data
- ✓ Current stock levels
- ✓ Pricing information
- ✓ Stock alerts and thresholds
- ✓ Category and classification
- ✓ Expiry dates (if provided)
- ✓ Batch information

## Best Practices

### 1. Data Preparation
- Remove blank rows and columns before export
- Validate data manually before upload
- Use consistent naming conventions
- Keep categories standardized

### 2. File Management
- Keep backup copies of source files
- Use descriptive filenames with dates (e.g., `inventory_2025-05-20.xlsx`)
- Store original CSV in a safe location
- Document any manual adjustments made

### 3. Regular Updates
- Schedule regular imports for ongoing updates
- Import incremental changes, not full resets
- Use the import history to track changes
- Periodically audit imported data

### 4. Error Handling
- Always check validation results before importing
- Fix all errors before attempting import
- Review warnings even though they're non-blocking
- Export reports after import to verify

## Examples

### Example 1: Basic Medicine Import
```
Medicine Name | Generic Name | Brand Name | Category | Current Stock | MRP | Purchase Rate | Manufacturer
Paracetamol 500mg | Paracetamol | Crocin | Antipyretic | 100 | 50.00 | 25.00 | GSK
Aspirin 100mg | Aspirin | Aspirin | Analgesic | 50 | 30.00 | 15.00 | Bayer
```

### Example 2: Complete Import with All Fields
```
Medicine Name | Generic Name | Brand Name | Category | Current Stock | MRP | Purchase Rate | Manufacturer | HSN Code | GST % | Unit Type | Min Stock | Reorder Qty | Batch No | Expiry Date | Barcode | Rack
Ibuprofen 200mg | Ibuprofen | Brufen | Anti-inflammatory | 75 | 40.00 | 20.00 | Abbott | 30041090 | 5 | PCS | 15 | 40 | B001 | 2025-12-31 | 1234567890 | A1
```

## Troubleshooting

### Issue: Upload fails with "Invalid file type"
**Solution**: Ensure file is CSV (.csv) or Excel (.xlsx/.xls) format

### Issue: Validation shows "Missing required columns"
**Solution**: Don't modify column headers. Download a fresh template and copy your data into it.

### Issue: Data not updating after successful import
**Solution**: Refresh the page or wait a few seconds. Data usually updates within 30 seconds.

### Issue: Some records import but others skip silently
**Solution**: Check the import history for error details. Invalid rows are logged with specific error messages.

### Issue: Numbers being truncated or converted incorrectly
**Solution**: Ensure numbers are not formatted as text. Remove any thousand separators or currency symbols.

## Support

For issues or questions about the import feature:
1. Check the Template Guide tab for detailed column descriptions
2. Review the validation error messages
3. Refer to this guide's troubleshooting section
4. Contact system administrator

## Keyboard Shortcuts

- **Ctrl+Enter**: Submit form (on import confirmation)
- **Ctrl+S**: Save downloaded template

## Limitations

- Maximum 10,000 records per import
- File size limit: 50MB
- Cannot import empty files
- Duplicate medicines are updated, not created again
- Expiry dates without batch numbers won't trigger alerts

## Future Enhancements

Planned features for the import system:
- Batch import scheduling
- Automated daily/weekly imports via API
- Custom field mapping
- Advanced duplicate detection
- Import templates for different file formats
- Multi-language support
- Barcode validation
- GRN and Purchase Order auto-linking
