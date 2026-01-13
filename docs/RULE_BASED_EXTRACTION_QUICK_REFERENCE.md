# Quick Reference: Rule-Based Table Extraction

## Extraction Pipeline Overview

```
PDF → Pages → Classify → OCR + YOLO → Column Alignment → Extract → Excel
      Images   (Pos/Trx)  Text+Boxes   (Spatial Rules)   (Rules)
```

---

## Page Classification

| Page Type   | Keywords                               | Result               |
| ----------- | -------------------------------------- | -------------------- |
| Position    | "Detailed positions" + "Last purchase" | Extract positions    |
| Position    | "Liquidity - Accounts" + "Valued in"   | Extract positions    |
| Transaction | "Transaction list" + "Valued in"       | Extract transactions |
| Other       | None match                             | Skip                 |

---

## Position Types

```
"Bonds - Bond investments"
"Equities - Equity investments"
"Equities - Structured products & derivatives"
"Liquidity - Accounts"
"Liquidity - Call deposits"
"Liquidity - Money market investments"
"Liquidity - FX swap & forward contracts"
```

---

## Column Detection Rules

### Position Table Columns

```
"By investment category"
"Description"
"Duration"
"Cost price"
"Market price"
"Market gain"
"Market value"
```

### Liquidity Account Columns

```
"By investment category"
"Description"
```

### Transaction Table Columns

```
"Trade date"
"Booking text"
"Transaction Tax"
"Custody account"
"Cost/Purchase price"
"Transaction price"
"Transaction gain"
"Transaction value"
```

---

## Row Filtering Rules

### Skip These Rows

✗ Header rows containing: "Trade date", "Valued in USD", "Value of net positions"

✗ Subtotal rows containing: "Total", "Subtotal"

✗ Empty rows: Description column is empty

---

## Transaction Type Mapping

| Booking Text                                           | Type             |
| ------------------------------------------------------ | ---------------- |
| "Sec. receipt against payment"                         | Purchase         |
| "Sec. delivery against payment" \| "Sale Spot"         | Sale             |
| Contains "FX Forward"                                  | FX Forward       |
| Contains "Reduction" \| "Repayment" \| "Interest Cap." | UBS Call Deposit |

---

## Key Extraction Functions

### ISIN Extraction

```
Search "Custody account" for "ISIN"
Extract: word after "ISIN" before first "-"
Example: "ISIN US0378331005" → "US0378331005"
```

### Currency Extraction

```
Search concatenated text for 180+ currency codes
Return: First match found (AED, AFN, ... ZWL)
```

### Quantity Extraction (Transactions)

```
Use: row_json["Transaction Tax"][0]
Extract: First numeric sequence
Handle: "100 000" → 100000
```

### Account Number Extraction

```
Pattern: \b\d{3}-\d{6}\.[A-Z0-9]+\b
Example matches: 546-880515.01, 546-880515.N1
Return: Last account number in list
```

### Date Conversion

```
Input format: DD.MM.YYYY
Output format: MM/DD/YYYY
Example: 31.03.2025 → 03/31/2025
```

### Security Name Cleaning

**Step 1: Remove quantity prefix**

```
Pattern: ^([0-9][0-9\s,\.]*)\s+(.*)$

Guard rules:
✓ Split if: has spaces/commas (thousands sep.) OR ≥5 digits
✗ Skip if: result starts with "%" (coupon rate)
✗ Skip if: single digit followed by text

Examples:
"100 000 4.625% Notes" → qty=100000, name="4.625% Notes"
"3.15% Notes ABC" → NO SPLIT (rate guard)
```

**Step 2: Remove account info from transaction names**

```
Remove: "You bought...", "You sold...", "ISIN" lines, account numbers
Join: Remaining lines with spaces
Result: Clean security name
```

---

## Data Validation Rules

### Number Validation

`is_number(s)`

- Can be converted to float

`is_number_strict(s)`

- Can be converted to float
- Maximum 1 decimal point
- Not equal to "0"
- If starts with "-", check remainder

### Account Number Format

```
Pattern: \d{3}-\d{6}\.[A-Z0-9]+
Valid: 546-880515.01, 546-880515.N1
Invalid: 12345.99, 546880515-01
```

---

## Column Alignment Rules

**Spatial Overlap Check:**

```
For each OCR box candidate:
  1. Calculate horizontal overlap with header box
  2. Min overlap ratio: 20% (default: 0.2)
  3. Optional: Center must be within header bounds
  4. Optional: Must be below header (for transactions) ✅ NEW
  5. Optional: Y-gap tolerance: 2.0 pixels ✅ NEW
  6. Include in column if passes check
```

**New Parameters (Recent Update):**

- `below_header_only`: If True, exclude boxes above header (prevents column misalignment)
- `y_gap_tol`: Y-coordinate gap tolerance (default 2.0 pixels) for determining if box is below header

---

## Position Data Output Template

```
{
  "Portfolio No.": "546-880515-01",
  "Type": "[Extracted Position Type]",
  "Account No": "[From Description[-1] or empty]",
  "Currency": "[USD, EUR, GBP, etc.]",
  "Quantity/ Amount": "[Numeric value]",
  "Security ID": "[ISIN code]",
  "Security name": "[Cleaned name]",
  "Cost price": "[Numeric value]",
  "Market price": "[Numeric value]",
  "Market value": "[Numeric value]",
  "Accrued interest": "[Value or empty]",
  "Valuation date": "03/31/25"
}
```

---

## Transaction Data Output Templates

### Trade (Purchase/Sale)

```
{
  "Client name": "GINKGO TREE GLOBAL ALLOCATION FUND",
  "Name/ Security": "[Cleaned name]",
  "Securities ID": "[ISIN]",
  "Transaction type": "Purchase" | "Sale",
  "Trade date": "MM/DD/YYYY",
  "Settlement date": "MM/DD/YYYY",
  "Currency": "[Currency code]",
  "Quantity": "[Numeric]",
  "Account no.": "[546-880515.XX]",
  "Foreign Unit Price": "[Numeric]",
  "Foreign Gross consideration": "[Numeric]",
  "Foreign Net consideration": "[Numeric]",
  "Net consideration": "[Numeric or empty]",
  "Accrued interest": "[Value or empty]"
}
```

### FX Forward

```
{
  "Client name": "GINKGO TREE GLOBAL ALLOCATION FUND",
  "Transaction type": "FX Forward",
  "Trade date": "MM/DD/YYYY",
  "Settlement date": "MM/DD/YYYY",
  "Rate": "[Exchange rate]",
  "Currency Buy": "[e.g., USD]",
  "Amount Buy": "[Numeric]",
  "Currency Sell": "[e.g., EUR]",
  "Amount Sell": "[Numeric]",
  "Account no. Buy": "[546-880515.XX]",
  "Account no. Sell": "[546-880515.XX]"
}
```

### UBS Call Deposit

```
{
  "Client name": "GINKGO TREE GLOBAL ALLOCATION FUND",
  "Description": "[From Booking text]",
  "Securities ID": "[ISIN]",
  "Transaction type": "UBS Call Deposit",
  "Trade date": "MM/DD/YYYY",
  "Settlement date": "MM/DD/YYYY",
  "Foreign Gross Amount/Interest": "[Numeric]",
  "Foreign Net Amount": "[Numeric]",
  "Account no.": "[546-880515.XX]"
}
```

---

## Error Handling Strategy

| Scenario                 | Behavior                             |
| ------------------------ | ------------------------------------ |
| ISIN not found           | Return empty string ""               |
| Currency not found       | Return empty string ""               |
| Account number not found | Return empty string ""               |
| Invalid date format      | Return None                          |
| Quantity parsing fails   | Return None or ""                    |
| Missing OCR text         | Use alternative columns if available |
| No data in field         | Return [] or "" depending on context |

---

## Performance Notes

- **YOLO Row Detection Threshold**: 0.8 (80% for both position and transaction rows)
- **Column Alignment Threshold**: 0.2 (20% overlap required)
- **OCR Box Filtering Threshold**: 0.8 (slightly relaxed to avoid missing boxes)
- **Below-Header Check**: 2.0 pixel gap tolerance for transaction alignment
- **OCR Models Used**:
  - Detection: `PP-OCRv5_server_det`
  - Recognition: `PP-OCRv5_server_rec`
  - YOLO: `yolo_broker_line_detect.pt`

**Recent Optimization (Latest Update):**

- Pre-compute header indices and boxes per column (avoid recalculation)
- Hard row validation: Check for booking_text and trade/settlement dates
- Stricter validation: Require ISIN, quantity, and account_no for trade rows

---

## Common OCR Errors Handled

| Error Type           | Handling                                             |
| -------------------- | ---------------------------------------------------- |
| "0" ↔ "O"            | Position qty: Try both variants, normalize to digits |
| Extra spaces         | Use regex `\s+` for whitespace normalization         |
| Special characters   | Remove with regex `[^0-9.\-]` for numbers            |
| Date formats         | Parse as DD.MM.YYYY, convert to MM/DD/YYYY           |
| Amount with currency | Extract digits, ignore currency symbols              |
| Empty text elements  | Filter out empty strings from row_text ✅ NEW        |
| Noisy rows           | Hard validation: require booking_text, dates ✅ NEW  |

---

## File Output Structure

```
outputs/
├── {task_id}/
│   ├── postion.xlsx          # Position data
│   ├── trade.xlsx            # Purchase/Sale transactions
│   ├── fx_tf.xlsx            # FX Forward transactions
│   └── other.xlsx            # UBS Call Deposits & other
```

---

## Debugging Tips

1. **Check Page Classification**: Enable debug logs to verify page type detection
2. **Inspect YOLO Detections**: Visualize detected table rows on image
3. **Verify Column Alignment**: Check which OCR boxes aligned to each column header
4. **Trace Extraction**: Add breakpoints in `PositionProcessor` or `TransactionProcessor`
5. **Validate Output**: Check generated Excel files for missing/incorrect data
6. **OCR Quality**: Lower thresholds if OCR has low confidence
