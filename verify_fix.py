
import re

def _parse_signed_number_string(s):
    try:
        return float(s.replace(",", "").replace(" ", ""))
    except:
        return ""

def test_logic(row_tokens, row_json, transaction_type="Increase", row_currency="USD"):
    print(f"Testing with tokens: {row_tokens}")
    
    qty_raw_list = row_json.get("Number/Amount", [])
    qty_raw = qty_raw_list[0].strip() if qty_raw_list else ""

    clean_qty = ""
    try:
        match_num = re.search(r"[\-\+]?[\d, ]+(?:\.\d+)?", qty_raw)
        if match_num:
            parsed_val = _parse_signed_number_string(match_num.group(0))
            if parsed_val != "":
                clean_qty = str(parsed_val)
    except Exception:
        clean_qty = ""
    
    print(f"Clean Qty: {clean_qty}")

    desc_str = ""
    if transaction_type == "Increase":
        max_idx = -1
        
        # 1. Locate Currency token
        if row_currency:
            for idx, t in enumerate(row_tokens):
                if t.strip() == row_currency:
                    max_idx = max(max_idx, idx)
        
        # 2. Locate Quantity tokens
        if qty_raw_list:
            for q_token in qty_raw_list:
                q_clean = q_token.strip()
                for idx, t in enumerate(row_tokens):
                    if t.strip() == q_clean:
                        max_idx = max(max_idx, idx)

        print(f"Max Index found: {max_idx}")

        if max_idx != -1 and max_idx < len(row_tokens) - 1:
            desc_tokens = row_tokens[max_idx+1:]
            desc_str = " ".join(desc_tokens).strip()
        else:
            desc_val = row_json.get("Description", [])
            desc_str = desc_val[0].strip() if desc_val else ""

    print(f"Result Description: '{desc_str}'")
    return desc_str

# Test Case 1: Ideal case
row_tokens_1 = ["USD", "1,000.00", "Description", "of", "increase"]
row_json_1 = {
    "Number/Amount": ["1,000.00"],
    "Description": ["Description of increase"] # Assume original logic might have captured this
}
assert test_logic(row_tokens_1, row_json_1) == "Description of increase"

# Test Case 2: Description currently captures quantity (simulated problem)
# If original description column overlapped, maybe row_json["Description"] was "1,000.00 Description"
row_tokens_2 = ["USD", "500", "Capital", "Increase"]
row_json_2 = {
    "Number/Amount": ["500"],
    "Description": ["500 Capital Increase"] # Overlapping
}
assert test_logic(row_tokens_2, row_json_2) == "Capital Increase"

# Test Case 3: Messy tokens
row_tokens_3 = ["Valued", "in", "USD", "10", "000", "New", "Inject"]
# Assume "10 000" was matched to Number
row_json_3 = {
    "Number/Amount": ["10", "000"],
    "Description": ["New Inject"]
}
# Here max_idx should be index of "000" (which is 4).
# "USD" is at 2.
# max_idx = 4.
# tokens[5:] = ["New", "Inject"]
assert test_logic(row_tokens_3, row_json_3) == "New Inject"

print("All tests passed!")
