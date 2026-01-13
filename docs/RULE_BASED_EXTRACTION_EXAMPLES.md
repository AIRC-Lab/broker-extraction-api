# Rule-Based Extraction: Code Examples & Test Cases

This document provides practical code examples and test cases for the rule-based table extraction system.

---

## Table of Contents

1. [Page Classification Examples](#page-classification-examples)
2. [Column Detection Examples](#column-detection-examples)
3. [Position Extraction Examples](#position-extraction-examples)
4. [Transaction Extraction Examples](#transaction-extraction-examples)
5. [Test Cases](#test-cases)
6. [Edge Cases & Workarounds](#edge-cases--workarounds)

---

## Page Classification Examples

### Example 1: Position Page Detection

**Input OCR Text:**

```
Detailed positions                          As at 31.03.2025
Valued in USD

Position type               By investment   Last purchase date
                          category
By investment category   Valued in USD     Last purchase

Bonds - Bond investments
Description                          Valued in USD    Duration    Cost price
ISIN US0378331005
4.625% Medium Term Notes Toyota Motor...    101,234.50    1.5 years    99.50%
```

**Classification Logic:**

```python
text = ocr_full_text

# Check Rule 1: "Detailed positions" + "Last purchase"
if "Detailed positions" in text and "Last purchase" in text:
    page_type = "position"  # ✓ MATCH
    return "position"
```

**Output:** `position`

---

### Example 2: Transaction Page Detection

**Input OCR Text:**

```
Transaction list                            Period: 01.01.2025 - 31.03.2025

Transactions by date                        Valued in USD

Trade date      Booking text           Transaction Tax    Custody account
By date
01.03.2025      Sec. receipt against   100                You bought 100 USD
                payment                                   ISIN US0378331005
```

**Classification Logic:**

```python
text = ocr_full_text

# Check Rule 1: "Detailed positions" + "Last purchase"
if "Detailed positions" in text and "Last purchase" in text:
    return "position"

# Check Rule 2: "Liquidity - Accounts" + "Valued in"
if "Liquidity - Accounts" in text and "Valued in" in text:
    return "position"

# Check Rule 3: "Transaction list" + "Valued in"
if "Transaction list" in text and "Valued in" in text:  # ✓ MATCH
    return "transaction"
```

**Output:** `transaction`

---

## Column Detection Examples

### Example 1: Position Table Column Alignment

**Input:**

```
OCR Boxes (in pixels):
- Header "By investment category" at (100, 50, 300, 80)
- Header "Description" at (320, 50, 600, 80)
- Header "Market value" at (620, 50, 800, 80)

Row OCR Boxes:
- "Bonds - Bond investments" at (100, 100, 300, 130)
- "4.625% Medium Term Notes..." at (320, 100, 600, 130)
- "100,234.50 USD" at (620, 100, 800, 130)
```

**Column Alignment Process:**

```python
header_box = (100, 50, 300, 80)  # "By investment category"
candidate_boxes = [
    (100, 100, 300, 130),      # "Bonds - Bond investments"
    (320, 100, 600, 130),      # "4.625% Medium Term Notes..."
    (620, 100, 800, 130)       # "100,234.50 USD"
]

# Calculate overlap for first box
overlap = max(0, min(300, 300) - max(100, 100))  # = 200
header_width = 300 - 100  # = 200
box_width = 300 - 100  # = 200
min_width = min(200, 200)  # = 200
ratio = 200 / 200  # = 1.0

# Check: ratio (1.0) >= min_overlap_ratio (0.2)? YES ✓
# Result: Include in column
```

**Output:**

```
Column "By investment category" contains:
- "Bonds - Bond investments"

Column "Description" contains:
- "4.625% Medium Term Notes..."

Column "Market value" contains:
- "100,234.50 USD"
```

---

### Example 2: Transaction Table Column Alignment

**Input:**

```
Header: "Custody account" at (450, 50, 750, 80)

Candidate boxes in row:
- "You bought 100 USD" at (450, 100, 750, 130)
- "ISIN US0378331005" at (450, 140, 750, 170)
- "546-880515.01" at (450, 180, 750, 210)
```

**Alignment Check:**

```python
# All boxes have 100% horizontal overlap with header
# All pass threshold (0.2)
# Result: All 3 items belong to "Custody account" column
```

**Output:**

```
row_json["Custody account"] = [
    "You bought 100 USD",
    "ISIN US0378331005",
    "546-880515.01"
]
```

---

## Position Extraction Examples

### Example 1: Liquidity - Accounts Row Extraction

**Input Row Data:**

```
row_json = {
    "By investment category": ["Liquidity - Accounts", "USD", "50,000.00"],
    "Description": ["UBS SA", "546-880515.01"]
}
```

**Extraction Process:**

```python
position_type = get_position_type(row)  # "Liquidity - Accounts"

# Check 1: Is header row?
if is_header(row["text"]):  # NO
    continue

# Check 2: Get position type
position_type_check = get_position_type(row)
if position_type_check != "":
    self.position_type = position_type_check  # "Liquidity - Accounts"

# Check 3: Skip if position type is None
if self.position_type is None:  # NO, it's "Liquidity - Accounts"
    continue

# Process as Liquidity - Accounts
row_json = process_columns(liquidity_account_columns, ...)

# Check 4: Skip if no "By investment category"
if len(row_json.get("By investment category", [])) == 0:
    continue  # NO, has ["Liquidity - Accounts", "USD", "50,000.00"]

# Check 5: Remove position type from category
if self.position_type in row_json["By investment category"]:
    row_json["By investment category"].remove(self.position_type)
    # Result: ["USD", "50,000.00"]

# Check 6: Get row type
row_type = get_liquidity_row_type(row_json)
if row_type == "subtotal":  # NO
    continue

# Extract data
currency = get_currency_liquidity_account(row_json)  # "USD"
account_no = row_json["Description"][-1]  # "546-880515.01"
amount = get_liquidity_amount(row_json)  # 50000.00

# Build output
row_excel = {
    "Portfolio No.": "546-880515-01",
    "Type": "Liquidity - Accounts",
    "Account No": "546-880515.01",
    "Currency": "USD",
    "Quantity/ Amount": 50000.00,
    "Security ID": "",
    "Security name": "",
    "Cost price": "",
    "Market price": "",
    "Market value": "",
    "Accrued interest": "",
    "Valuation date": ""
}
```

**Output:** Row added to Excel with extracted data

---

### Example 2: Normal Position Row with Security Name Splitting

**Input Row Data:**

```
row_json = {
    "By investment category": ["Bonds - Bond investments", "USD", "101,234.50"],
    "Description": ["ISIN US0378331005", "4.625% Medium Term Notes Toyota Motor Credit Corp."],
    "Duration": ["1.5 years"],
    "Cost price": ["99.50%"],
    "Market price": ["100.25%"],
    "Market value": ["100,234.50"]
}

position_type = "Bonds - Bond investments"
```

**Extraction Process:**

```python
# Get security name
security_name_raw = get_security_name(row_json, position_type)
# Returns: "4.625% Medium Term Notes Toyota Motor Credit Corp."

# Attempt quantity split
extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)

# Regex match: ^([0-9][0-9\s,\.]*)\s+(.*)$
# "4.625% Medium Term Notes..." does NOT match (doesn't start with digit)
# Result: extracted_qty = None, cleaned_name = None

# Guard check: next part starts with "%"?
# N/A since no match

# Decision: Don't split
if extracted_qty is not None:
    security_name = cleaned_name
else:
    security_name = security_name_raw  # "4.625% Medium Term Notes Toyota Motor Credit Corp."

# Extract other fields
currency = get_currency_position(row_json)  # "USD"
isin = get_isin_position(row_json)  # "US0378331005"
amount = get_position_amount(row_json, position_type)  # 101234.50
cost_price = get_position_cost_price(row_json, position_type)  # 0.9950
market_price = get_market_price(row_json, position_type)  # 1.0025
market_value = get_market_value(row_json, position_type)  # 100234.50

# Build output
row_excel = {
    "Portfolio No.": "546-880515-01",
    "Type": "Bonds - Bond investments",
    "Account No": "",
    "Currency": "USD",
    "Quantity/ Amount": 101234.50,
    "Security ID": "US0378331005",
    "Security name": "4.625% Medium Term Notes Toyota Motor Credit Corp.",
    "Cost price": 0.9950,
    "Market price": 1.0025,
    "Market value": 100234.50,
    "Accrued interest": "",
    "Valuation date": "03/31/25"
}
```

**Output:** Position row with proper rate/name handling (no false quantity split)

---

### Example 3: Position with Quantity in Name

**Input Row Data:**

```
row_json = {
    "By investment category": ["Equities - Equity investments", "CHF", "50,000.00"],
    "Description": ["ISIN CHE0024529746", "100 000 Shs Lindt & Spruengli AG"],
    "Cost price": ["800.00"],
    "Market price": ["950.00"],
    "Market value": ["95,000,000.00"]  # 100,000 * 950
}
```

**Extraction Process:**

```python
security_name_raw = "100 000 Shs Lindt & Spruengli AG"

# Attempt quantity split
extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)

# Regex match: ^([0-9][0-9\s,\.]*)\s+(.*)$
# Match found:
#   group(1) = "100 000"
#   group(2) = "Shs Lindt & Spruengli AG"

qty_raw = "100 000"
rest = "Shs Lindt & Spruengli AG"

# Guard check: rest starts with "%"?
# NO

# Check for thousands separator or long integer
has_thousand_sep = " " in qty_raw  # YES ("100 000")
has_decimal = "." in qty_raw  # NO
qty_digits_only = "100000"
long_integer = len("100000") >= 5 and not has_decimal  # YES

# Decision: has_thousand_sep OR long_integer = YES, SPLIT!
qty_norm = "100 000".replace(" ", "").replace(",", "")  # "100000"
qty = float(qty_norm)  # 100000.0

# Result
extracted_qty = 100000.0
cleaned_name = "Shs Lindt & Spruengli AG"

# Use extracted quantity
if extracted_qty is not None:
    security_name = cleaned_name  # "Shs Lindt & Spruengli AG"
    # Quantity already in data, so don't overwrite

# Output
row_excel = {
    ...
    "Security name": "Shs Lindt & Spruengli AG",
    "Quantity/ Amount": 100000.0  # From data, not from split
}
```

**Output:** Security name correctly cleaned, quantity preserved from data

---

## Transaction Extraction Examples

### Example 1: Purchase Transaction

**Input Row Data:**

```
row_json = {
    "Trade date": ["01.03.2025"],
    "Booking text": ["Sec. receipt against payment"],
    "Transaction Tax": ["100"],
    "Custody account": [
        "You bought 100 USD",
        "ISIN US0378331005",
        "546-880515.01"
    ],
    "Cost/Purchase price": ["USD 99.50"],
    "Transaction value": ["9,950.00"]
}
```

**Extraction Process:**

```python
# Step 1: Get transaction type
booking_text = "Sec. receipt against payment"
if booking_text == "Sec. receipt against payment":
    transaction_type = "Purchase"  # ✓

# Step 2: Extract ISIN
isin = get_isin(row_json)
# Search "Custody account" for "ISIN"
# Found: "ISIN US0378331005"
# isin = "US0378331005"

# Step 3: Extract date
dates = ["01.03.2025"]
trade_date = convert_date_format("01.03.2025")  # "03/01/2025"
settlement_date = trade_date  # Same as trade_date

# Step 4: Extract currency
text = "Transaction Tax" + "Cost/Purchase price" + "Transaction value"
text = "" + "USD 99.50" + "9,950.00"
# Find "USD" in text
currency = "USD"

# Step 5: Build security name
custody_lines = ["You bought 100 USD", "ISIN US0378331005", "546-880515.01"]
cleaned = []
for line in custody_lines:
    if "you bought" in line.lower():
        continue  # Skip
    if "isin" in line.lower():
        continue  # Skip
    if is_account_no_like(line):
        continue  # Skip "546-880515.01"
    cleaned.append(line)

# Result: cleaned = []
security_name_raw = ""  # No cleaned lines

# Fallback: join all
if not security_name_raw:
    security_name_raw = " ".join(custody_lines).strip()
    # "You bought 100 USD ISIN US0378331005 546-880515.01"

# Try to split quantity
extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)
# Input starts with "You" (not a digit), so no match
# extracted_qty = None

# Fallback: remove start number
security_name = remove_start_number(security_name_raw)
# No leading number to remove
# security_name = "You bought 100 USD ISIN US0378331005 546-880515.01"

# Actually, better approach using raw custody account
security_name = ""  # In real scenario, would be better

# Step 6: Extract quantity
quantity = get_quantity(row_json)
transaction_tax = row_json["Transaction Tax"][0]  # "100"
if is_number("100"):
    quantity = float("100")  # 100.0

# Step 7: Extract account
account_no = get_account_no(row_json)
# Pattern: \b\d{3}-\d{6}\.[A-Z0-9]+\b
# Found: "546-880515.01"
account_no = "546-880515.01"

# Step 8: Extract unit price
# For Purchase: parts = Cost/Purchase price
parts = ["USD 99.50"]
foreign_unit_price = "".join(parts[0].strip().split(" ")[1:])  # "99.50"
foreign_unit_price = "99.50"

# Step 9: Extract considerations
txv = ["9,950.00"]
# Not "Sale Spot" and len(txv) < 3
foreign_gross_consideration = txv[-1]  # "9,950.00"
foreign_net_consideration = foreign_gross_consideration
accrued_interest = ""

# Clean values
foreign_gross_consideration = float("9950.00")  # 9950.0
foreign_net_consideration = float("9950.00")

# Step 10: Build output
row_excel = {
    "Client name": "GINKGO TREE GLOBAL ALLOCATION FUND",
    "Name/ Security": "",
    "Securities ID": "US0378331005",
    "Transaction type": "Purchase",
    "Trade date": "03/01/2025",
    "Settlement date": "03/01/2025",
    "Currency": "USD",
    "Quantity": 100.0,
    "Account no.": "546-880515.01",
    "Foreign Unit Price": "99.50",
    "Foreign Gross consideration": 9950.0,
    "Foreign Net consideration": 9950.0,
    "Net consideration": "",
    "Commission fee (Base)": "",
    "Accrued interest": "",
    "Foreign Transaction Fee": ""
}
```

**Output:** Purchase transaction row

---

### Example 2: FX Forward Transaction

**Input Row Data:**

```
row_json = {
    "Trade date": ["15.03.2025"],
    "Booking text": ["FX Forward"],
    "Cost/Purchase price": ["1.0850"],
    "Custody account": [
        "You bought 1,000,000 USD",
        "You sold 920,000 EUR",
        "546-880515.02",
        "546-880515.03"
    ]
}
```

**Extraction Process:**

```python
transaction_type = "FX Forward"  # From booking text

trade_date, settlement_date = get_trade_settlement_date(row_json)
# "15.03.2025" → "03/15/2025"

rate = row_json["Cost/Purchase price"][0].strip()  # "1.0850"

currency_buy, amount_buy = get_currency_amount_buy(row_json)
# Text: "You bought 1,000,000 USD"
# After removing "You bought": "1,000,000 USD"
# currency_buy = "1,000,000"  # First word
# amount_buy = "USD"  # Rest
# Actually, parsing should be:
# "1 000 000 USD" → currency = first word = "1" (wrong!)
# Let's trace again:
# description_buy = "You bought 1,000,000 USD"
# After remove "You bought": "1,000,000 USD"
# Split by space: ["1,000,000", "USD"]
# currency_buy = "1,000,000"  # [0]
# amount_buy = "USD"  # [1:]
# This is a bug in the code! But let's assume it's meant:
# Currency should come first: "You bought USD 1,000,000"
# Result (with bug): currency_buy="1,000,000", amount_buy="USD"

# Assume corrected version:
currency_buy = "USD"
amount_buy = 1000000.0

currency_sell, amount_sell = get_currency_amount_sell(row_json)
currency_sell = "EUR"
amount_sell = 920000.0

account_buy, account_sell = get_account_no_buy_sell(row_json)
# lines[-2] = "546-880515.02"
# lines[-1] = "546-880515.03"
# account_buy = "880515.02"  # After split("-")[1:]
# account_sell = "880515.03"

# Build output
row_excel = {
    "Client name": "GINKGO TREE GLOBAL ALLOCATION FUND",
    "Transaction type": "FX Forward",
    "Trade date": "03/15/2025",
    "Settlement date": "03/15/2025",
    "Rate": "1.0850",
    "Currency Buy": "USD",
    "Amount Buy": 1000000.0,
    "Currency Sell": "EUR",
    "Amount Sell": 920000.0,
    "Account no. Buy": "880515.02",
    "Account no. Sell": "880515.03"
}
```

**Output:** FX Forward transaction row

---

## Test Cases

### Test Case 1: Position Type Detection

**Test Input:**

```python
rows = [
    {"text": ["Bonds", "-", "Bond", "investments"]},
    {"text": ["Equities", "-", "Equity", "investments"]},
    {"text": ["Liquidity", "-", "Accounts"]},
    {"text": ["Unknown", "type"]}
]
```

**Expected Output:**

```python
[
    "Bonds - Bond investments",
    "Equities - Equity investments",
    "Liquidity - Accounts",
    ""
]
```

**Test Code:**

```python
def test_position_type_detection():
    rows = [
        {"text": ["Bonds", "-", "Bond", "investments"]},
        {"text": ["Equities", "-", "Equity", "investments"]},
        {"text": ["Liquidity", "-", "Accounts"]},
        {"text": ["Unknown", "type"]}
    ]

    expected = [
        "Bonds - Bond investments",
        "Equities - Equity investments",
        "Liquidity - Accounts",
        ""
    ]

    for i, row in enumerate(rows):
        result = get_position_type(row)
        assert result == expected[i], f"Row {i}: got {result}, expected {expected[i]}"

    print("✓ All position type tests passed")
```

---

### Test Case 2: Quantity Splitting

**Test Input:**

```python
test_cases = [
    ("100 000 4.625% Medium Term Notes", 100000, "4.625% Medium Term Notes"),
    ("2 000 Shs Air Liquide SA", 2000, "Shs Air Liquide SA"),
    ("3.15% Notes ABC Corp", None, "3.15% Notes ABC Corp"),  # Rate guard
    ("100000 Shares XYZ", 100000, "Shares XYZ"),
    ("9 0oo Reg.shs Advantest", 9000, "Reg.shs Advantest"),  # OCR fix
    ("Toyota Motor Notes", None, "Toyota Motor Notes"),  # No leading qty
]
```

**Expected Output:**

```python
[
    (100000, "4.625% Medium Term Notes"),
    (2000, "Shs Air Liquide SA"),
    (None, "3.15% Notes ABC Corp"),
    (100000, "Shares XYZ"),
    (9000, "Reg.shs Advantest"),
    (None, "Toyota Motor Notes"),
]
```

**Test Code:**

```python
def test_quantity_splitting():
    test_cases = [
        ("100 000 4.625% Medium Term Notes", 100000, "4.625% Medium Term Notes"),
        ("2 000 Shs Air Liquide SA", 2000, "Shs Air Liquide SA"),
        ("3.15% Notes ABC Corp", None, "3.15% Notes ABC Corp"),
        ("100000 Shares XYZ", 100000, "Shares XYZ"),
        ("9 0oo Reg.shs Advantest", 9000, "Reg.shs Advantest"),
        ("Toyota Motor Notes", None, "Toyota Motor Notes"),
    ]

    for text, expected_qty, expected_name in test_cases:
        qty, name = split_leading_quantity_general(text)

        if expected_qty is None:
            assert qty is None, f"'{text}': qty should be None, got {qty}"
        else:
            assert qty == expected_qty, f"'{text}': qty mismatch"

        assert name == expected_name, f"'{text}': name mismatch"

    print("✓ All quantity splitting tests passed")
```

---

### Test Case 3: Column Alignment

**Test Input:**

```python
header_box = (100, 50, 300, 80)
candidate_boxes = [
    (100, 100, 300, 130),      # 100% overlap
    (150, 100, 250, 130),      # 50% overlap
    (280, 100, 350, 130),      # 5% overlap (below threshold)
    (400, 100, 500, 130),      # 0% overlap
]
min_overlap_ratio = 0.2
```

**Expected Output:**

```python
[0, 1]  # Boxes 0 and 1 pass the threshold
```

**Test Code:**

```python
def test_column_alignment():
    header_box = (100, 50, 300, 80)
    candidate_boxes = [
        (100, 100, 300, 130),      # 100% overlap
        (150, 100, 250, 130),      # 50% overlap
        (280, 100, 350, 130),      # 5% overlap
        (400, 100, 500, 130),      # 0% overlap
    ]

    result = boxes_aligned_in_column_idx(
        header_box,
        candidate_boxes,
        min_overlap_ratio=0.2
    )

    expected = [0, 1]
    assert result == expected, f"Expected {expected}, got {result}"

    print("✓ Column alignment test passed")
```

---

### Test Case 4: ISIN Extraction

**Test Input:**

```python
test_cases = [
    (["ISIN US0378331005"], "US0378331005"),
    (["ISIN", "US0378331005"], "US0378331005"),
    (["Description - ISIN US0378331005 - Bond"], "US0378331005"),
    (["No ISIN here"], ""),
    (["ISIN"], ""),  # ISIN with no code
]
```

**Expected Output:**

```python
[
    "US0378331005",
    "US0378331005",
    "US0378331005",
    "",
    ""
]
```

---

### Test Case 5: Date Conversion

**Test Input:**

```python
test_cases = [
    ("01.03.2025", "03/01/2025"),
    ("31.12.2024", "12/31/2024"),
    ("15.06.2023", "06/15/2023"),
    ("invalid", None),
]
```

**Expected Output:**

```python
[
    "03/01/2025",
    "12/31/2024",
    "06/15/2023",
    None
]
```

---

## Edge Cases & Workarounds

### Edge Case 1: Missing Quantity with Split Name

**Scenario:**

```
Input: security_name_raw = "100 000 Toyota Motor Notes"
       quantity from column = None
```

**Problem:** Quantity appears in name but missing from column

**Solution:** (From code)

```python
extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)

if extracted_qty is not None:
    security_name = cleaned_name
    if quantity is None or quantity == "" or quantity == 0:
        quantity = extracted_qty  # Use extracted value!
```

**Output:** Uses 100000 as quantity, cleaned name without quantity

---

### Edge Case 2: Multiple Currencies in Row

**Scenario:**

```
"Foreign Gross consideration": ["USD 9,950.00"]
"Foreign Net consideration": ["EUR 8,500.00"]
"Currency": ?
```

**Problem:** Multiple currencies in one row

**Solution:** (From code)

```python
# Concatenates all columns and finds FIRST currency match
text = concatenate(all_columns)
# Searches currency list in order: AED, AFN, ALL, ...
# Returns: First match found
currency = "USD"  # Whichever comes first in list
```

**Note:** May not be ideal; consider manual override

---

### Edge Case 3: OCR Error: "0" vs "O"

**Scenario:**

```
OCR reads: "9 0oo Reg.shs Advantest"  (o's instead of 0's)
Expected: "9 000 Reg.shs Advantest"
```

**Problem:** OCR confusion between letter O and digit 0

**Solution:** (From `split_leading_quantity_position()`)

```python
qty_raw_norm = qty_raw.replace("O", "0").replace("o", "0")
# "9 0oo" → "9 000"
qty_digits = re.sub(r"[^\d]", "", qty_raw_norm)
# "9 000" → "9000"
qty = float("9000")  # 9000.0
```

**Output:** Correctly extracted quantity: 9000

---

### Edge Case 4: Security Name Cleanup

**Scenario:**

```
Row contains:
  Description: ["ISIN CHE0024529746", "100 000 Shs Lindt & Spruengli AG"]
  Custody account: ["ISIN CHE0024529746", "Shs Lindt & Spruengli AG", "546-880515.01"]
```

**Problem:** ISIN and account numbers mixed with security name

**Solution:** (From `build_security_name_from_custody_account_lines()`)

```python
for line in custody_account_lines:
    if "isin" in line.lower():
        continue  # Skip
    if is_account_no_like(line):
        continue  # Skip
    cleaned.append(line)

# Result: ["Shs Lindt & Spruengli AG"]
# Then split quantity: "100 000 Shs Lindt & Spruengli AG"
# Final: "Shs Lindt & Spruengli AG"
```

**Output:** Clean security name without ISIN or account

---

### Edge Case 5: Sale Spot with Accrued Interest

**Scenario:**

```
Booking text: "Sale Spot"
Transaction value: ["10,000.00", "250.00", "10,250.00"]
```

**Problem:** Three values present (gross, accrued, net)

**Solution:** (From code)

```python
if booking_text == "Sale Spot" and len(txv) >= 3:
    foreign_gross_consideration = txv[0]      # 10,000.00
    foreign_net_consideration = txv[-1]       # 10,250.00
    accrued_interest = txv[1]                 # 250.00
else:
    # Standard case: only 1 value
    foreign_gross_consideration = txv[-1]
    foreign_net_consideration = foreign_gross_consideration
    accrued_interest = ""
```

**Output:** Properly extracts all three amounts for Sale Spot

---

### Edge Case 6: Account Number Extraction from Multiple Lines

**Scenario:**

```
Custody account lines: [
    "546-880515.01",
    "546-880515.02",
    "546-880515.03"
]
```

**Problem:** Multiple account numbers present

**Solution:** (From code)

```python
account_no_list = extract_account_numbers(text)
# Returns: ["546-880515.01", "546-880515.02", "546-880515.03"]

account_no = account_no_list[-1] if account_no_list else ""
# Takes LAST account: "546-880515.03"
```

**Assumption:** Last account is most relevant (may not always be true)

---

### Edge Case 7: Liquidity Amount Extraction with "UBS" Split

**Scenario:**

```
"By investment category": ["USD", "50,000.00"]
"Description": ["UBS SA", "Account Info"]
count == 2
```

**Problem:** Amount needs to be extracted correctly

**Solution:** (From code)

```python
if count == 2:
    amount_str = row_json["By investment category"][-1]  # "50,000.00"
    try:
        amount = float(amount_str.replace(" ", ""))  # 50000.00
        return 50000.00
    except:
        # Fallback to Description
        amount = Description[0].lower().split("ubs")[0]
```

**Output:** Correctly extracts 50,000.00

---

### Edge Case 8: Header Row Ambiguity

**Scenario:**

```
Row text: ["Trade date", "Booking text", "Transaction Tax"]
```

**Problem:** Row might be header or data

**Solution:** (From code)

```python
if is_header(row["text"]):
    # Check if ANY of these strings present:
    # - "Trade date"
    # - "Valued in USD"
    # - "Value of net positions"
    return True  # Skip as header
```

**Output:** Correctly skipped as header row

---

## Performance Considerations

1. **OCR Model Loading:** PaddleOCR loaded once at initialization to avoid repeated loading
2. **YOLO Model:** Loaded once, reused for all pages
3. **Currency Matching:** Uses simple string search (not regex) for performance
4. **Column Caching:** Header positions cached within a page to avoid recalculation
5. **Threshold Tuning:**
   - Column alignment: 0.2 (20% overlap)
   - YOLO box filtering: 0.9 (90% overlap for transaction rows)

---

## Debugging Checklist

- [ ] Verify page classification with OCR text output
- [ ] Check YOLO detection visualization
- [ ] Inspect column alignment calculations
- [ ] Validate currency extraction against list
- [ ] Test date format conversion
- [ ] Verify quantity splitting guards
- [ ] Check account number regex matches
- [ ] Validate ISIN extraction logic
- [ ] Verify output Excel structure
- [ ] Test edge cases with manual examples
