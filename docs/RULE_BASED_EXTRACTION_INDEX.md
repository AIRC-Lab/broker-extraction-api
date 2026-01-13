# Rule-Based Table Extraction Documentation - Index

Complete documentation of all rule-based extraction rules for the Broker Extraction API.

## 📚 Documentation Files Created

### 1. **RULE_BASED_EXTRACTION_DOCUMENTATION.md** (Complete Reference)

- **Purpose:** Comprehensive technical documentation of all extraction rules
- **Contents:**
  - Extraction pipeline overview
  - Page classification rules
  - Position table extraction rules (detailed)
  - Transaction table extraction rules (detailed)
  - Helper functions and utility rules
  - Data output formats
  - Summary of critical rules
- **Best for:** Deep technical understanding, implementation reference
- **Size:** ~2000 lines

### 2. **RULE_BASED_EXTRACTION_QUICK_REFERENCE.md** (Fast Lookup)

- **Purpose:** Quick reference guide for common tasks
- **Contents:**
  - Extraction pipeline diagram
  - Page classification table
  - Position types list
  - Column detection rules
  - Row filtering rules
  - Transaction type mapping
  - Key extraction functions summary
  - Data validation rules
  - Output templates
  - Error handling strategy
  - Common OCR errors
  - File output structure
  - Debugging tips
- **Best for:** Quick lookup, during development, debugging
- **Size:** ~600 lines

### 3. **RULE_BASED_EXTRACTION_EXAMPLES.md** (Practical Implementation)

- **Purpose:** Real-world examples and test cases
- **Contents:**
  - Page classification examples (with actual OCR data)
  - Column detection examples (with pixel coordinates)
  - Position extraction examples (step-by-step walkthrough)
  - Transaction extraction examples (detailed flows)
  - Test cases (with expected outputs)
  - Edge cases and workarounds
  - Performance considerations
  - Debugging checklist
- **Best for:** Learning the system, implementation testing, debugging
- **Size:** ~1200 lines

### 4. **RULE_BASED_EXTRACTION_RULES_INDEX.md** (This File)

- **Purpose:** Navigation and overview of all documentation
- **Contents:**
  - Index of all documentation files
  - Quick navigation guide
  - Rule categories summary
  - File locations
- **Best for:** Finding the right documentation
- **Size:** ~400 lines

---

## 🔍 Rule Categories Overview

### Page Classification (2 documents)

- **Doc:** RULE_BASED_EXTRACTION_DOCUMENTATION.md → Page Classification Rules
- **Doc:** RULE_BASED_EXTRACTION_QUICK_REFERENCE.md → Page Classification
- **Doc:** RULE_BASED_EXTRACTION_EXAMPLES.md → Page Classification Examples

**Rules:**

- Detailed positions + Last purchase → Position page
- Liquidity - Accounts + Valued in → Position page
- Transaction list + Valued in → Transaction page
- Other → Skip

---

### Position Table Extraction (2 documents)

- **Doc:** RULE_BASED_EXTRACTION_DOCUMENTATION.md → Position Table Extraction Rules
- **Doc:** RULE_BASED_EXTRACTION_EXAMPLES.md → Position Extraction Examples

**Key Rules:**

- Column detection: By investment category, Description, Duration, Cost/Market prices
- Position type classification (Bonds, Equities, Liquidity types)
- Row filtering (skip headers, subtotals, empty rows)
- Quantity splitting (with rate guards)
- Currency/ISIN extraction
- Amount calculation
- Output field mapping

---

### Transaction Table Extraction (2 documents)

- **Doc:** RULE_BASED_EXTRACTION_DOCUMENTATION.md → Transaction Table Extraction Rules
- **Doc:** RULE_BASED_EXTRACTION_EXAMPLES.md → Transaction Extraction Examples

**Key Rules:**

- Column detection: Trade date, Booking text, Custody account, etc.
- Transaction type classification (Purchase, Sale, FX Forward, UBS Call Deposit)
- Row filtering (skip headers)
- ISIN/Currency/Date extraction
- Security name building and cleaning
- Quantity and account number extraction
- Three output formats: Trade, FX Forward, Other
- Currency buy/sell and account mapping

---

### Spatial Rules (Column Alignment)

- **Doc:** RULE_BASED_EXTRACTION_DOCUMENTATION.md → Spatial Rules for Column Alignment
- **Doc:** RULE_BASED_EXTRACTION_QUICK_REFERENCE.md → Column Alignment Rules
- **Doc:** RULE_BASED_EXTRACTION_EXAMPLES.md → Column Detection Examples

**Rules:**

- Horizontal overlap ratio minimum: 0.2 (20%)
- Optional center-within-header check
- YOLO box filtering: threshold 0.8-0.9
- Box intersection calculation (IoU-like)

---

### Helper Functions & Utilities

- **Doc:** RULE_BASED_EXTRACTION_DOCUMENTATION.md → Helper Functions & Utility Rules

**Functions:**

- `boxes_aligned_in_column_idx()` - Column alignment
- `ocr_boxes_inside_yolo()` - Row detection
- `is_header()` - Header identification
- `get_position_type()` - Position type detection
- `is_number()`, `is_number_strict()` - Number validation
- `extract_account_numbers()` - Account pattern matching
- `convert_date_format()` - Date conversion
- `split_leading_quantity_general()` - Quantity extraction
- And many more...

---

## 🎯 How to Use This Documentation

### For Quick Understanding

1. Start with **RULE_BASED_EXTRACTION_QUICK_REFERENCE.md**
2. Review the "Extraction Pipeline Overview" section
3. Check "Key Extraction Functions" for specific tasks

### For Implementation

1. Read **RULE_BASED_EXTRACTION_DOCUMENTATION.md** (complete reference)
2. Check **RULE_BASED_EXTRACTION_EXAMPLES.md** for your use case
3. Refer to code in:
   - `app/utils.py` - Helper functions
   - `app/services/position_processor.py` - Position logic
   - `app/services/transaction_processor.py` - Transaction logic
   - `app/services/pdf_processor.py` - Overall pipeline

### For Debugging

1. Review **RULE_BASED_EXTRACTION_QUICK_REFERENCE.md** → Error Handling Strategy
2. Check **RULE_BASED_EXTRACTION_EXAMPLES.md** → Edge Cases & Workarounds
3. Use Debugging Checklist from Examples document

### For Testing

1. Use test cases from **RULE_BASED_EXTRACTION_EXAMPLES.md**
2. Refer to test inputs/outputs
3. Implement custom tests based on patterns shown

---

## 📋 Complete Rule Checklist

### Page Classification Rules

- [ ] "Detailed positions" + "Last purchase" → Position
- [ ] "Liquidity - Accounts" + "Valued in" → Position
- [ ] "Transaction list" + "Valued in" → Transaction

### Position Type Rules (9 types)

- [ ] Bonds - Bond investments
- [ ] Equities - Equity investments
- [ ] Equities - Structured products & derivatives
- [ ] Liquidity - Accounts
- [ ] Liquidity - Call deposits
- [ ] Liquidity - Money market investments
- [ ] Liquidity - FX swap & forward contracts

### Column Detection Rules

- [ ] Position: By investment category, Description, Duration, Cost/Market prices
- [ ] Liquidity: By investment category, Description
- [ ] Transaction: Trade date, Booking text, Tax, Custody account, Prices, Values

### Row Filtering Rules

- [ ] Skip header rows ("Trade date", "Valued in USD", "Value of net positions")
- [ ] Skip subtotal rows ("Total", "Subtotal")
- [ ] Skip empty rows (no Description)

### Extraction Rules

- [ ] Currency extraction (180+ currencies)
- [ ] ISIN extraction (from "ISIN" keyword)
- [ ] Account number extraction (pattern: \d{3}-\d{6}\.[A-Z0-9]+)
- [ ] Date conversion (DD.MM.YYYY → MM/DD/YYYY)
- [ ] Quantity splitting (with guards)
- [ ] Security name cleaning
- [ ] Price/Amount parsing

### Transaction Type Rules

- [ ] "Sec. receipt against payment" → Purchase
- [ ] "Sec. delivery against payment" / "Sale Spot" → Sale
- [ ] "FX Forward" → FX Forward
- [ ] "Reduction" / "Repayment" / "Interest Cap." → UBS Call Deposit

### Output Rules

- [ ] Position: Portfolio No., Type, Currency, Quantity/Amount, Security ID, name, prices
- [ ] Trade: Client name, Security, ISIN, Type, Dates, Currency, Quantity, Unit price, Consideration
- [ ] FX Forward: Client name, Type, Dates, Rate, Buy/Sell currency amounts, Accounts
- [ ] UBS Call Deposit: Client name, Description, Securities ID, Type, Dates, Amount

---

## 🔗 Related Code Files

### Core Processing

- `app/main.py` - FastAPI endpoints
- `app/tasks.py` - Celery task orchestration
- `app/utils.py` - All extraction rules and helper functions
- `app/services/pdf_processor.py` - PDF to image conversion, OCR, YOLO
- `app/services/position_processor.py` - Position-specific extraction
- `app/services/transaction_processor.py` - Transaction-specific extraction
- `app/services/excel_exporter.py` - Excel output

### Configuration

- `config.py` - Application settings
- `requirements.txt` - Dependencies
- `docker-compose.yml` - Docker setup
- `Dockerfile` - Container definition

### Models

- `app/weights/yolo_broker_line_detect.pt` - YOLO row detection model

---

## 🚀 Implementation Workflow

### 1. PDF Upload

```
POST /soa/upload-pdf/ → task_id
```

### 2. Processing (Celery Task)

```
Step 1: PDF to Images (pdf_to_images)
Step 2: For each page:
  - Classify (position/transaction)
  - Perform OCR (PaddleOCR)
  - Extract info (position_processor or transaction_processor)
Step 3: Export to Excel (excel_exporter)
```

### 3. Download Results

```
GET /download-excel/{task_id}/ → List of Excel files
GET /download-excel-file/{task_id}/{filename} → Download file
```

### 4. Output Files

```
outputs/
└── {task_id}/
    ├── postion.xlsx (position data)
    ├── trade.xlsx (purchase/sale)
    ├── fx_tf.xlsx (FX forward)
    └── other.xlsx (UBS call deposits)
```

---

## 📊 Data Flow Diagram

```
PDF Document
    ↓
[pdf_to_images] → PIL Images
    ↓
For each page:
    ↓
    ├─ [classify_page] → "position" or "transaction"
    │
    ├─ [perform_ocr] → OCR boxes + text
    │
    ├─ [YOLO predict] → Row detection boxes
    │
    ├─ [extract_info] → Structured data
    │  │
    │  └─ If position:
    │     ├─ [PositionProcessor.process]
    │     ├─ Detect position type
    │     ├─ Align columns
    │     ├─ Extract fields
    │     └─ → Position rows
    │
    │  └─ If transaction:
    │     ├─ [TransactionProcessor.process]
    │     ├─ Detect transaction type
    │     ├─ Align columns
    │     ├─ Extract fields
    │     └─ → Trade/FX/Other rows
    ↓
[excel_exporter] → Excel files
    ↓
outputs/{task_id}/*.xlsx
```

---

## 🎓 Learning Path

### Beginner

1. Read: QUICK_REFERENCE.md (5 min)
2. Understand: Extraction Pipeline Overview
3. Review: Position Types, Transaction Types
4. Check: Simple examples from EXAMPLES.md

### Intermediate

1. Read: DOCUMENTATION.md (30 min)
2. Study: Position/Transaction extraction rules
3. Review: Spatial rules, column alignment
4. Practice: Implement test cases from EXAMPLES.md

### Advanced

1. Deep dive: All documentation files
2. Review: Source code in app/services/
3. Implement: Custom extraction rules
4. Debug: Using edge cases from EXAMPLES.md
5. Optimize: Performance tuning

---

## 🔧 Troubleshooting Guide

### Issue: Wrong page classification

- **Check:** Page contains required keywords
- **Doc:** QUICK_REFERENCE.md → Page Classification
- **Fix:** May need to add custom keywords

### Issue: Missing extracted data

- **Check:** Is row being skipped (header/subtotal)?
- **Doc:** QUICK_REFERENCE.md → Row Filtering Rules
- **Fix:** Adjust skip conditions if needed

### Issue: Incorrect security name

- **Check:** Quantity splitting or cleanup rules
- **Doc:** EXAMPLES.md → Edge Cases
- **Fix:** Review split_leading_quantity_general logic

### Issue: Wrong currency extracted

- **Check:** Multiple currencies in row
- **Doc:** EXAMPLES.md → Edge Cases → Multiple Currencies
- **Fix:** Currency extraction picks first match

### Issue: Account number missing

- **Check:** Account pattern in Custody account field
- **Doc:** QUICK_REFERENCE.md → Account Number Format
- **Fix:** Pattern is `\d{3}-\d{6}\.[A-Z0-9]+`

### Issue: Date parsing fails

- **Check:** Date format is DD.MM.YYYY
- **Doc:** QUICK_REFERENCE.md → Date Conversion
- **Fix:** Support custom date formats if needed

---

## 📝 Version Information

- **Created:** January 2026
- **Framework:** FastAPI + Celery
- **OCR:** PaddleOCR
- **ML Model:** YOLO (ultralytics)
- **Python:** 3.9+
- **Documentation Type:** Rule-based extraction system

---

## 📞 Quick Links in Documentation

### DOCUMENTATION.md (Main Reference)

- [Page Classification Rules](RULE_BASED_EXTRACTION_DOCUMENTATION.md#page-classification-rules)
- [Position Table Extraction](RULE_BASED_EXTRACTION_DOCUMENTATION.md#position-table-extraction-rules)
- [Transaction Table Extraction](RULE_BASED_EXTRACTION_DOCUMENTATION.md#transaction-table-extraction-rules)
- [Helper Functions](RULE_BASED_EXTRACTION_DOCUMENTATION.md#helper-functions--utility-rules)
- [Data Output Format](RULE_BASED_EXTRACTION_DOCUMENTATION.md#data-output-format)

### QUICK_REFERENCE.md (Fast Lookup)

- [Page Classification](RULE_BASED_EXTRACTION_QUICK_REFERENCE.md#page-classification)
- [Position Types](RULE_BASED_EXTRACTION_QUICK_REFERENCE.md#position-types)
- [Column Detection](RULE_BASED_EXTRACTION_QUICK_REFERENCE.md#column-detection-rules)
- [Key Extraction Functions](RULE_BASED_EXTRACTION_QUICK_REFERENCE.md#key-extraction-functions)
- [Error Handling](RULE_BASED_EXTRACTION_QUICK_REFERENCE.md#error-handling-strategy)

### EXAMPLES.md (Implementation)

- [Page Classification Examples](RULE_BASED_EXTRACTION_EXAMPLES.md#page-classification-examples)
- [Position Extraction Examples](RULE_BASED_EXTRACTION_EXAMPLES.md#position-extraction-examples)
- [Transaction Extraction Examples](RULE_BASED_EXTRACTION_EXAMPLES.md#transaction-extraction-examples)
- [Test Cases](RULE_BASED_EXTRACTION_EXAMPLES.md#test-cases)
- [Edge Cases](RULE_BASED_EXTRACTION_EXAMPLES.md#edge-cases--workarounds)

---

## ✅ Verification Checklist

When implementing or debugging, verify:

- [ ] Page is correctly classified (position/transaction)
- [ ] Position type detected from row text
- [ ] Column headers correctly aligned
- [ ] Header rows skipped (Trade date, Valued in USD, etc.)
- [ ] Subtotal rows skipped
- [ ] Currency extracted from concatenated columns
- [ ] ISIN extracted after "ISIN" keyword
- [ ] Account number matches pattern
- [ ] Date converted to MM/DD/YYYY format
- [ ] Quantity split correctly (with rate guard)
- [ ] Security name cleaned (no ISIN, account, quantity)
- [ ] All required fields present in output
- [ ] Excel file created with correct structure
- [ ] No exceptions during processing

---

## 📄 File Statistics

| Document             | Lines     | Content Type        | Best For                      |
| -------------------- | --------- | ------------------- | ----------------------------- |
| DOCUMENTATION.md     | ~2000     | Technical Reference | Deep learning, implementation |
| QUICK_REFERENCE.md   | ~600      | Quick Lookup        | Daily use, debugging          |
| EXAMPLES.md          | ~1200     | Code Examples       | Testing, learning             |
| INDEX.md (this file) | ~400      | Navigation          | Finding right doc             |
| **TOTAL**            | **~4200** | Complete System     | Full understanding            |

---

## 🎯 Next Steps

1. **Read** the Quick Reference to get oriented
2. **Study** the main Documentation for your specific area
3. **Review** Examples and test cases for implementation
4. **Implement** using code templates from Examples
5. **Debug** using the Troubleshooting Guide
6. **Test** using the provided test cases
7. **Optimize** based on Performance Notes

---
