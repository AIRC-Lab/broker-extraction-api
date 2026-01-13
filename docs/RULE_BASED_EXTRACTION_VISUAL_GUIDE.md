# Rule-Based Extraction: Visual Guide & Architecture

Complete visual representation of the extraction system architecture and rule flows.

---

## 1. Overall System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROKER EXTRACTION API                     │
└─────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
            ┌──────────────┐         ┌──────────────┐
            │ FastAPI App  │         │   Celery     │
            │  (REST API)  │────────▶│  Workers     │
            └──────────────┘         └──────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
            ┌──────────────┐                        ┌──────────────────┐
            │     Redis    │◀───────────────────────│  PDF Processor    │
            │ (Task Queue) │                        │  - OCR (Paddle)   │
            └──────────────┘                        │  - YOLO Detection │
                                                    │  - Rule Extraction│
                                                    └──────────────────┘
                                                            │
                                                    ┌───────┴────────┐
                                                    ▼                ▼
                                            ┌──────────────┐  ┌──────────────┐
                                            │   Position   │  │ Transaction  │
                                            │  Processor   │  │  Processor   │
                                            └──────────────┘  └──────────────┘
                                                    │                │
                    ┌───────────────────────────────┴────────────────┤
                    ▼                                                 ▼
            ┌──────────────────────────────────────────────────────────────┐
            │              Excel Exporter                                   │
            │  ├─ Position Data (postion.xlsx)                             │
            │  ├─ Trade Transactions (trade.xlsx)                          │
            │  ├─ FX Transactions (fx_tf.xlsx)                             │
            │  └─ Other Transactions (other.xlsx)                          │
            └──────────────────────────────────────────────────────────────┘
```

---

## 2. PDF Processing Pipeline

```
Input PDF
    │
    ▼
┌─────────────────────────────────┐
│   pdf_to_images()               │
│   Convert PDF to PIL Images     │
└─────────────────────────────────┘
    │
    ├─── Page 1 Image
    ├─── Page 2 Image
    ├─── Page 3 Image
    └─── ...
    │
    ▼
FOR EACH PAGE:
    │
    ├──────────────────────────────────────┐
    │  Step 1: Classify Page               │
    │  ┌────────────────────────────────┐  │
    │  │ classify_page(image)           │  │
    │  │ - Perform OCR to get text      │  │
    │  │ - Match against keywords       │  │
    │  │ - Return: "position" | "tx"    │  │
    │  └────────────────────────────────┘  │
    │                                       │
    │  Result: page_type = "position"      │
    └──────────────────────────────────────┘
    │
    ├──────────────────────────────────────┐
    │  Step 2: Perform OCR                 │
    │  ┌────────────────────────────────┐  │
    │  │ perform_ocr(image)             │  │
    │  │ - Extract text + bounding box  │  │
    │  │ - PaddleOCR model              │  │
    │  │ - Return: ocr_result           │  │
    │  └────────────────────────────────┘  │
    │                                       │
    │  Result: OCR boxes + text list       │
    └──────────────────────────────────────┘
    │
    ├──────────────────────────────────────┐
    │  Step 3: Extract Info                │
    │  ┌────────────────────────────────┐  │
    │  │ extract_info(image,ocr,type)   │  │
    │  │                                │  │
    │  │ if type == "position":         │  │
    │  │   └─ PositionProcessor.process │  │
    │  │                                │  │
    │  │ if type == "transaction":      │  │
    │  │   └─ TransactionProcessor.process
    │  │                                │  │
    │  │ Return: extracted_data         │  │
    │  └────────────────────────────────┘  │
    │                                       │
    │  Result: Structured data rows        │
    └──────────────────────────────────────┘
    │
    ▼
AGGREGATE DATA:
    ├─ extracted_data_list["position"][]
    └─ extracted_data_list["transaction"]
        ├─ ["trade_info"][]
        ├─ ["fx_tf_info"][]
        └─ ["other_info"][]
    │
    ▼
┌─────────────────────────────────┐
│  excel_exporter()               │
│  Write to Excel files           │
└─────────────────────────────────┘
    │
    ▼
Output: Excel Files
    ├─ postion.xlsx
    ├─ trade.xlsx
    ├─ fx_tf.xlsx
    └─ other.xlsx
```

---

## 3. Position Processing Pipeline

```
Position Page Input:
  - image: PIL Image
  - ocr_result: OCR boxes + text
  - page_type: "position"

    │
    ▼
┌──────────────────────────────────────┐
│  STEP 1: Row Detection (YOLO)        │
│  yolo_model.predict(image)           │
│  Result: [[x1,y1,x2,y2], ...]        │
└──────────────────────────────────────┘
    │
    ├─ Row 1: [100, 100, 800, 130]
    ├─ Row 2: [100, 150, 800, 180]
    └─ Row 3: [100, 200, 800, 230]
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 2: OCR Box Filtering           │
│  FOR EACH yolo_box:                  │
│    ocr_boxes_inside_yolo()           │
│    Filter OCR boxes within row       │
│                                      │
│  Result: Row data dictionary         │
│  row_list[]["text"]  = OCR text      │
│  row_list[]["index"] = OCR indices   │
└──────────────────────────────────────┘
    │
    ├─ Row 1: ["Bonds - Bond", "ISIN...", "4.625%", "101234.50"]
    ├─ Row 2: ["Equities", "Apple", "150", "15000.00"]
    └─ Row 3: ["Total", "50000", "...]  ◄─── Skip (subtotal)
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 3: Header Detection & Skip     │
│  is_header(row["text"])              │
│  Skip if contains:                   │
│    - "Trade date"                    │
│    - "Valued in USD"                 │
│    - "Value of net positions"        │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 4: Position Type Detection     │
│  get_position_type(row)              │
│  Match row text against patterns:    │
│    - "Bonds - Bond" → "Bonds - ..."  │
│    - "Equities" → "Equities - ..."   │
│    - "Liquidity" → "Liquidity - ..." │
└──────────────────────────────────────┘
    │
    ├─ Row 1: "Bonds - Bond investments"
    └─ Row 2: "Equities - Equity investments"
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 5: Column Alignment             │
│  boxes_aligned_in_column_idx()       │
│  FOR EACH column_header:             │
│    Find OCR boxes aligned in column  │
│    Threshold: 20% horizontal overlap │
│                                      │
│  Result: row_json dictionary        │
│  row_json["By investment cat"] = [] │
│  row_json["Description"] = []       │
│  row_json["Market value"] = []      │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 6: Data Extraction              │
│  Extract fields per position type:   │
│                                      │
│  For "Liquidity - Accounts":        │
│    - Currency from category         │
│    - Amount from category           │
│    - Account from Description       │
│                                      │
│  For "Normal" positions:             │
│    - Currency: get_currency()        │
│    - ISIN: get_isin_position()       │
│    - Amount: get_position_amount()   │
│    - Prices: get_*_price()           │
│    - Name: get_security_name()       │
│      ├─ Clean with name            │
│      └─ Split leading quantity      │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 7: Row Type Filtering          │
│  get_row_type(row_json)              │
│  Skip if:                            │
│    - "Subtotal" or "Total" found    │
│    - Description empty               │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 8: Build Output Row            │
│  row_excel = {                       │
│    "Portfolio No.": "546-880515-01", │
│    "Type": position_type,            │
│    "Currency": currency,             │
│    "Quantity/Amount": amount,        │
│    "Security ID": isin,              │
│    "Security name": name,            │
│    "Cost price": cost_price,         │
│    "Market price": market_price,     │
│    "Market value": market_value,     │
│    ...                               │
│  }                                   │
└──────────────────────────────────────┘
    │
    ▼
Output: Position data rows
```

---

## 4. Transaction Processing Pipeline

```
Transaction Page Input:
  - image: PIL Image
  - ocr_result: OCR boxes + text
  - page_type: "transaction"

    │
    ▼
┌──────────────────────────────────────┐
│  STEP 1: Row Detection (YOLO)        │
│  Same as Position                    │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 2: OCR Box Filtering           │
│  Threshold: 0.9 (90% for transactions)
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 3: Header Detection & Skip     │
│  is_header(row["text"])              │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 4: Column Alignment             │
│  Align to transaction columns:       │
│    - Trade date                      │
│    - Booking text                    │
│    - Transaction Tax                 │
│    - Custody account                 │
│    - Cost/Purchase price             │
│    - Transaction price               │
│    - Transaction gain                │
│    - Transaction value               │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  STEP 5: Transaction Type Detection  │
│  get_transaction_type(row_json)      │
│                                      │
│  Booking text patterns:              │
│    "Sec. receipt..." → "Purchase"    │
│    "Sec. delivery..." → "Sale"       │
│    "Sale Spot" → "Sale"              │
│    "FX Forward" → "FX Forward"       │
│    "Reduction/Repayment" → "UBS..."  │
└──────────────────────────────────────┘
    │
    ├─ Type: "Purchase"
    ├─ Type: "Sale"
    ├─ Type: "FX Forward"
    └─ Type: "UBS Call Deposit"
    │
    ▼
    FOR EACH transaction_type:
    │
    ├─────────────────────────────────┐
    │  Type: PURCHASE / SALE          │
    │  ┌──────────────────────────┐   │
    │  │ Extract:                 │   │
    │  │ - ISIN get_isin()        │   │
    │  │ - Currency get_currency()│   │
    │  │ - Date get_trade_...()   │   │
    │  │ - Quantity get_quantity()│   │
    │  │ - Account get_account()  │   │
    │  │ - Unit price get_unit...│   │
    │  │ - Consideration get_..() │   │
    │  │ - Security name build_...│   │
    │  │   ├─ Clean up           │   │
    │  │   └─ Split quantity     │   │
    │  └──────────────────────────┘   │
    │                                 │
    │  Output: trade_information[]    │
    └─────────────────────────────────┘
    │
    ├─────────────────────────────────┐
    │  Type: FX FORWARD               │
    │  ┌──────────────────────────┐   │
    │  │ Extract:                 │   │
    │  │ - Date get_trade_...()   │   │
    │  │ - Rate from Cost/Purchase│   │
    │  │ - Currency Buy/Sell      │   │
    │  │ - Amount Buy/Sell        │   │
    │  │ - Account Buy/Sell       │   │
    │  └──────────────────────────┘   │
    │                                 │
    │  Output: fx_tf_information[]    │
    └─────────────────────────────────┘
    │
    └─────────────────────────────────┐
       Type: UBS CALL DEPOSIT / OTHER│
       ┌──────────────────────────┐   │
       │ Extract:                 │   │
       │ - ISIN get_isin()        │   │
       │ - Date get_trade_...()   │   │
       │ - Description from text  │   │
       │ - Amount get_...()       │   │
       │ - Account get_account()  │   │
       └──────────────────────────┘   │
                                      │
       Output: other_information[]    │
       ─────────────────────────────┘
    │
    ▼
Output: Aggregated transaction data
    ├─ trade_information[]
    ├─ fx_tf_information[]
    └─ other_information[]
```

---

## 5. Column Alignment Algorithm

```
Input: header_box, candidate_boxes, min_overlap_ratio

    │
    ▼
┌─────────────────────────────────────────────────┐
│ FOR EACH candidate box:                         │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │ Step 1: Normalize coordinates             │ │
│   │   hx1, hy1, hx2, hy2 = header_box       │ │
│   │   bx1, by1, bx2, by2 = candidate_box    │ │
│   └───────────────────────────────────────────┘ │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │ Step 2: Calculate horizontal overlap      │ │
│   │   overlap = max(0, min(hx2,bx2) - ...)   │ │
│   │   Example: hx1=100, hx2=300              │ │
│   │            bx1=150, bx2=250              │ │
│   │            overlap = min(300,250) - ...  │ │
│   │                    = 250 - 150 = 100     │ │
│   └───────────────────────────────────────────┘ │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │ Step 3: Calculate minimum width           │ │
│   │   hw = hx2 - hx1                         │ │
│   │   bw = bx2 - bx1                         │ │
│   │   w_min = min(hw, bw)                    │ │
│   │   Example: hw = 200, bw = 100            │ │
│   │            w_min = 100                    │ │
│   └───────────────────────────────────────────┘ │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │ Step 4: Calculate overlap ratio           │ │
│   │   ratio = overlap / w_min                 │ │
│   │   Example: ratio = 100 / 100 = 1.0       │ │
│   └───────────────────────────────────────────┘ │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │ Step 5: Apply threshold check             │ │
│   │   IF ratio >= min_overlap_ratio:          │ │
│   │       INCLUDE in column                   │ │
│   │   Example: 1.0 >= 0.2 → YES ✓           │ │
│   └───────────────────────────────────────────┘ │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │ Step 6: Optional center check             │ │
│   │   IF center_within:                       │ │
│   │       cx = (bx1 + bx2) / 2               │ │
│   │       IF NOT (hx1 <= cx <= hx2):         │ │
│   │           SKIP box                        │ │
│   └───────────────────────────────────────────┘ │
│                                                 │
└─────────────────────────────────────────────────┘
    │
    ▼
Output: Indices of aligned boxes
```

**Visual Example:**

```
Header Box:        ┌─────────────────────────┐
                   │ "Market value" header   │
                   └─────────────────────────┘
                   100                      300

Candidate 1:       ┌──────────────────────┐
                   │ "100,234.50"         │  ← 100% overlap ✓
                   └──────────────────────┘
                   100                   250

Candidate 2:       ┌──────────────────────┐
                   │ "50,000.00"          │  ← 50% overlap ✓
                   └──────────────────────┘
                   150                   250

Candidate 3:                    ┌──────────┐
                                │ "X"      │  ← 5% overlap ✗
                                └──────────┘
                                280       320
                                (below threshold)
```

---

## 6. Quantity Splitting Decision Tree

```
Input: security_name_raw

    │
    ▼
┌──────────────────────────────────┐
│ Does text start with digit?      │
│ Regex: ^[0-9]                    │
└──────────────────────────────────┘
    │
    ├─ NO: Return (None, original_text)
    │
    └─ YES: Continue
        │
        ▼
    ┌──────────────────────────────────┐
    │ Match pattern:                   │
    │ ^([0-9][0-9\s,\.]*)\s+(.*)$     │
    └──────────────────────────────────┘
        │
        ├─ NO MATCH: Return (None, original_text)
        │
        └─ MATCH:
            qty_raw = group(1)  # "100 000"
            rest = group(2)     # "4.625% Notes..."
            │
            ▼
        ┌──────────────────────────────────┐
        │ GUARD CHECK 1: Rate?             │
        │ Does rest start with "%"?        │
        └──────────────────────────────────┘
            │
            ├─ YES: Return (None, original_text)
            │       Reason: Avoid splitting "3.15% Notes..."
            │
            └─ NO: Continue
                │
                ▼
            ┌──────────────────────────────────┐
            │ Check quantity characteristics:  │
            │                                  │
            │ has_thousand_sep =              │
            │   (" " in qty_raw) OR            │
            │   ("," in qty_raw)               │
            │                                  │
            │ has_decimal =                    │
            │   "." in qty_raw                 │
            │                                  │
            │ qty_digits = remove non-digits  │
            │                                  │
            │ long_integer =                   │
            │   len(digits) >= 5 AND           │
            │   NOT has_decimal                │
            └──────────────────────────────────┘
                │
                ▼
            ┌──────────────────────────────────┐
            │ GUARD CHECK 2: Valid quantity?   │
            │ (has_thousand_sep OR long_int)   │
            └──────────────────────────────────┘
                │
                ├─ NO: Return (None, original_text)
                │
                └─ YES: Continue
                    │
                    ▼
                ┌──────────────────────────────────┐
                │ Convert to float                 │
                │ qty = float(qty_norm)            │
                └──────────────────────────────────┘
                    │
                    ├─ EXCEPTION: Return (None, original)
                    │
                    └─ SUCCESS:
                        │
                        ▼
                    ┌──────────────────────────────────┐
                    │ Return (qty_float, rest_text)    │
                    │ Example: (100000.0, "4.625%...")  │
                    └──────────────────────────────────┘

Examples:
─────────────────────────────────────────────────────────────

"100 000 4.625% Notes"
    └─ Has thousand sep (space) → YES
    └─ Rest starts with % → Guard fails → NO SPLIT ✗

"2 000 Shs Air Liquide"
    └─ Has thousand sep (space) → YES
    └─ Rest starts with % → NO
    └─ SPLIT → (2000.0, "Shs Air Liquide") ✓

"100000 Shares"
    └─ Long integer (5 digits) → YES
    └─ SPLIT → (100000.0, "Shares") ✓

"3.15% Notes ABC"
    └─ Rest starts with % → Guard fails → NO SPLIT ✗

"Toyota Motor Notes"
    └─ Doesn't start with digit → NO SPLIT ✗
```

---

## 7. Transaction Type Decision Tree

```
Input: Booking text field

    │
    ▼
┌──────────────────────────────────────────┐
│ Check exact matches first:               │
└──────────────────────────────────────────┘
    │
    ├─ booking_text == "Sec. receipt against payment"
    │   │
    │   └─ RETURN: "Purchase"
    │
    ├─ booking_text == "Sec. delivery against payment"
    │   │
    │   └─ RETURN: "Sale"
    │
    ├─ booking_text == "Sale Spot"
    │   │
    │   └─ RETURN: "Sale"
    │
    └─ Continue to next checks
    │
    ▼
┌──────────────────────────────────────────┐
│ Check for substring matches:             │
└──────────────────────────────────────────┘
    │
    ├─ "FX Forward" in booking_text
    │   │
    │   └─ RETURN: "FX Forward"
    │
    ├─ ("Reduction" OR "Repayment" OR "Interest Cap.") in text
    │   │
    │   └─ RETURN: "UBS Call Deposit"
    │
    └─ Continue to default
    │
    ▼
┌──────────────────────────────────────────┐
│ If no match:                             │
│ RETURN: booking_text.title()             │
└──────────────────────────────────────────┘

Example mappings:
────────────────────────────────────────────
"Sec. receipt against payment" → "Purchase"
"Sec. delivery against payment" → "Sale"
"Sale Spot" → "Sale"
"FX Forward" → "FX Forward"
"Reduction" → "UBS Call Deposit"
"Coupon Payment" → "Coupon Payment"
```

---

## 8. Currency Extraction Flow

```
Input: All row column values

    │
    ▼
┌─────────────────────────────────────────────┐
│ Concatenate search text:                    │
│   text = (Transaction Tax +                 │
│           Cost/Purchase price +             │
│           Transaction value)                │
│                                             │
│ Example: "" + "USD 99.50" + "9,950.00"    │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ FOR EACH currency in [AED, AFN, ..., ZWL]: │
│                                             │
│   IF currency_code in text:                 │
│     RETURN currency_code                    │
│                                             │
│   Example:                                  │
│   ├─ "USD" in "USD 99.50" → RETURN "USD"  │
│   └─ Match found, stop searching           │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ If no currency found:                       │
│ RETURN "" (empty string)                    │
└─────────────────────────────────────────────┘

Search order: [AED, AFN, ALL, ..., ZWL] (180+ codes)

Note: Returns FIRST match found, may not be ideal
      if multiple currencies in row
```

---

## 9. Data Extraction Rule Hierarchy

```
POSITION DATA EXTRACTION
├─ Row Detection (YOLO)
│   └─ 0.8-0.9 threshold for inclusion
├─ Header/Subtotal Filtering
│   ├─ Skip: "Trade date", "Valued in USD", etc.
│   └─ Skip: "Total", "Subtotal" rows
├─ Position Type Detection
│   └─ 9 types: Bonds, Equities, Liquidity variants
├─ Column Alignment
│   ├─ Minimum 20% horizontal overlap
│   └─ Match OCR boxes to columns
├─ Field Extraction
│   ├─ Currency: 180+ currency codes
│   ├─ ISIN: After "ISIN" keyword
│   ├─ Amount: From category values
│   ├─ Prices: From price columns
│   └─ Security Name:
│       ├─ Get from Description
│       ├─ Remove ISIN/Account
│       └─ Split leading quantity (with guards)
├─ Type-Specific Logic
│   └─ Liquidity vs. Normal positions
└─ Output Format
    └─ Standard Excel schema

TRANSACTION DATA EXTRACTION
├─ Row Detection (YOLO, 0.9 threshold)
├─ Header/Subtotal Filtering
├─ Transaction Type Detection
│   └─ 4 types: Purchase, Sale, FX Forward, UBS
├─ Column Alignment
├─ Field Extraction
│   ├─ ISIN: From Custody account
│   ├─ Currency: From concatenated text
│   ├─ Dates: Parse and convert format
│   ├─ Quantity: From Transaction Tax
│   ├─ Account: Last account in list
│   ├─ Prices/Amounts: Type-specific
│   └─ Security Name: Build from Custody account
├─ Type-Specific Logic
│   ├─ Purchase/Sale: Standard fields
│   ├─ FX Forward: Currency pairs
│   └─ UBS Call: Deposit-specific
└─ Output Format
    └─ 3 variants: Trade, FX, Other
```

---

## 10. Error Recovery Paths

```
GENERIC ERROR HANDLING
├─ TRY: Primary extraction method
│   ├─ SUCCESS: Use extracted value
│   └─ FAIL: Continue to fallback
├─ FALLBACK 1: Alternative field
│   ├─ SUCCESS: Use fallback value
│   └─ FAIL: Continue to fallback
├─ FALLBACK 2: Default value or empty
│   ├─ Empty string: ""
│   ├─ Zero: 0 or 0.0
│   ├─ None: None
│   └─ Empty list: []
└─ RESULT: Row processed with partial data

SPECIFIC EXAMPLES
─────────────────────────────────────

Currency Extraction:
  ├─ Try: Search in Transaction Tax
  ├─ Fallback 1: Search in Cost/Purchase price
  ├─ Fallback 2: Search in Transaction value
  └─ Result: "" (empty) if not found

Account Number:
  ├─ Try: Extract from Custody account
  ├─ Fallback: Return "" (empty)
  └─ Result: Last account if multiple exist

Security Name:
  ├─ Try: Build from Custody account
  ├─ Fallback: Join all Custody lines
  ├─ Cleanup: Remove ISIN/Account lines
  ├─ Split: Leading quantity
  └─ Result: Cleaned name or original text

Amount:
  ├─ Try: Parse Transaction value
  ├─ Fallback: Parse alternative column
  ├─ Guard: Validate numeric format
  └─ Result: Float or "" (empty)
```

---

## 11. Data Type Conversions

```
FIELD: Currency
  Input:  "USD", "EUR", "GBP", ... (180+ codes)
  Output: String (3-letter code)
  Example: "USD" → "USD"

FIELD: Quantity/Amount
  Input:  "100 000", "100000", "100,000"
  Process: Remove separators → convert to float
  Output: Float
  Example: "100 000" → 100000.0

FIELD: ISIN
  Input:  Text containing "ISIN XXXXXXXXXXXXX"
  Process: Extract after "ISIN" keyword
  Output: String (12-character code)
  Example: "ISIN US0378331005" → "US0378331005"

FIELD: Account Number
  Input:  "546-880515.01" or "546-880515.N1"
  Process: Regex match: \d{3}-\d{6}\.[A-Z0-9]+
  Output: String
  Example: "546-880515.01" → "546-880515.01"

FIELD: Date
  Input:  "31.03.2025" (DD.MM.YYYY)
  Process: Parse and reformat
  Output: "03/31/2025" (MM/DD/YYYY)
  Example: "31.03.2025" → "03/31/2025"

FIELD: Price/Percentage
  Input:  "99.50%", "100.25%", "99.50"
  Process: Extract numeric, remove %, divide by 100 if %
  Output: Float
  Example: "99.50%" → 0.9950

FIELD: Security Name
  Input:  "100 000 Toyota Motor Credit Corp."
  Process: Split quantity, remove account/ISIN
  Output: String
  Example: "100 000 Toyota..." → "Toyota Motor..."
```

---

## 12. Threshold Values & Parameters

```
COLUMN ALIGNMENT
├─ Minimum horizontal overlap: 0.2 (20%)
├─ Center within header: False (optional)
└─ Below header only: False (optional)

YOLO DETECTION
├─ Position rows threshold: 0.8 (80%)
├─ Transaction rows threshold: 0.9 (90%)
└─ Reason: Transactions more densely packed

QUANTITY SPLITTING
├─ Minimum digit length (no sep): 5 digits
├─ Thousand separators: space, comma, dot
├─ Rate guard: Skip if result starts with %
└─ Decimal guard: No decimal point for long integers

DATE PARSING
├─ Input format: DD.MM.YYYY
├─ Output format: MM/DD/YYYY
└─ Valid date check: Parse with strptime

CURRENCY MATCHING
├─ Code length: 3 letters
├─ Codes supported: 180+
└─ Search method: String contains (case-insensitive)

ACCOUNT NUMBER
├─ Pattern: \d{3}-\d{6}\.[A-Z0-9]+
├─ Example: 546-880515.01
└─ Selection: Last account if multiple
```

---

## 13. Summary: Complete Information Flow

```
INPUT: PDF Document
  ↓
[PDF → Images]
  ↓
[FOR EACH PAGE]
  ├─ [Classify: Position/Transaction]
  ├─ [Perform OCR: Text + Boxes]
  ├─ [YOLO: Detect Rows]
  ├─ [Process Rows]
  │   ├─ [Align Columns]
  │   ├─ [Detect Type]
  │   ├─ [Extract Fields]
  │   │   ├─ [Currency: 180+ codes]
  │   │   ├─ [ISIN: After keyword]
  │   │   ├─ [Amount: Parse numeric]
  │   │   ├─ [Date: Convert format]
  │   │   ├─ [Account: Regex match]
  │   │   └─ [Name: Split & clean]
  │   └─ [Build Output Row]
  ├─ [Filter Rows]
  │   ├─ [Skip Headers]
  │   ├─ [Skip Subtotals]
  │   └─ [Skip Empty]
  └─ [Aggregate Data]
  ↓
[Excel Export]
  ├─ postion.xlsx (positions)
  ├─ trade.xlsx (trades)
  ├─ fx_tf.xlsx (fx forwards)
  └─ other.xlsx (deposits)
  ↓
OUTPUT: Excel Files
```

---
