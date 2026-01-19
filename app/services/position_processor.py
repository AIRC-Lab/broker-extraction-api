from typing import List, Any
from PIL import Image
from app.utils import *
import math
import numpy as np
import re
from decimal import Decimal


class PositionProcessor:
    """A processor for extracting and refining positional information
    from OCR results using a YOLO object detection model."""

    def __init__(self) -> None:
        self.position_type = None
        self.portfolio_no = None

        # ✅ FIX: was missing -> caused AttributeError -> skipped ALL rows
        self.valuation_date = ""

    def _format_number_output(self, v):
        """
        Normalize number formatting for output:
          - remove thousand separators (space / ',' / '.' depending on locale)
          - decimal separator is always '.'
          - do NOT add decimals for integers
          - do NOT round
        Returns string (or "" if not parseable)
        """
        if v is None:
            return ""

        # If already Decimal, keep exact value (no rounding), render without scientific notation
        if isinstance(v, Decimal):
            # Decimal('100000') -> '100000'
            # Decimal('1234.26') -> '1234.26'
            return format(v, "f")

        # If numeric primitives
        if isinstance(v, (int, float)):
            # Avoid float artifacts by converting via string
            s = str(v).strip()
        else:
            s = str(v).strip()

        if not s:
            return ""

        # normalize minus variants
        s = s.replace("−", "-").replace("–", "-")

        # keep only likely numeric chars
        s_clean = re.sub(r"[^0-9\-\+\s,\.()]", "", s).strip()
        if not s_clean:
            return ""

        # parentheses negative
        neg_by_paren = False
        if "(" in s_clean and ")" in s_clean:
            neg_by_paren = True

        s_no_paren = s_clean.replace("(", "").replace(")", "").strip()
        if not s_no_paren:
            return ""

        # Decide decimal separator by last occurrence heuristic (same as utils logic)
        dot_pos = s_no_paren.rfind(".")
        comma_pos = s_no_paren.rfind(",")

        decimal_sep = None
        if dot_pos != -1 and comma_pos != -1:
            decimal_sep = "," if comma_pos > dot_pos else "."
        elif comma_pos != -1 and dot_pos == -1:
            # if looks like thousands grouping: 1,234 -> thousands
            if re.search(r",\d{3}(?:[^\d]|$)", s_no_paren):
                decimal_sep = None
            else:
                decimal_sep = ","
        else:
            decimal_sep = "."

        normalized = s_no_paren.replace(" ", "")

        if decimal_sep == ",":
            # dot as thousands, comma as decimal
            normalized = normalized.replace(".", "")
            normalized = normalized.replace(",", ".")
        else:
            # comma as thousands
            normalized = normalized.replace(",", "")

        # keep only sign, digits, dot
        normalized = re.sub(r"[^0-9\-\+\.]", "", normalized).strip()
        if not normalized:
            return ""

        # validate by Decimal but return string
        try:
            dv = Decimal(normalized)
            if neg_by_paren and dv > 0:
                normalized = "-" + normalized.lstrip("+").lstrip("-")
            # IMPORTANT: do not force decimals; Decimal('100000') stays '100000'
            # If normalized is like '100000.' (rare), clean it.
            if normalized.endswith("."):
                normalized = normalized[:-1]
            return normalized
        except Exception:
            return ""

    def process(
        self,
        yolo_model: Any,
        image: Image.Image,
        ocr_result: List[dict]
    ) -> List[dict]:

        detection_result = yolo_model.predict(image)[0].boxes.xyxy.tolist()
        ceil_det_box = [[math.ceil(x) for x in yolo_box] for yolo_box in detection_result]
        sorted_det_boxes = sorted(ceil_det_box, key=lambda box: box[1])

        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]

        # ---------------------------------------------------------
        # ✅ PRE-COMPUTE HEADER INDEX + HEADER BOX PER COLUMN
        # to make column matching stable even if OCR is slightly different
        # ---------------------------------------------------------
        header_idx_map = {}
        header_box_map = {}

        for col_name in position_columns:
            idx_header = get_index_by_name(col_name, ocr_text)
            header_idx_map[col_name] = idx_header
            if idx_header is not None:
                header_box_map[col_name] = ocr_box[idx_header]
            else:
                header_box_map[col_name] = None

        # Liquidity table headers
        header_idx_map_liq = {}
        header_box_map_liq = {}
        for col_name in liquidity_account_columns:
            idx_header = get_index_by_name(col_name, ocr_text)
            header_idx_map_liq[col_name] = idx_header
            if idx_header is not None:
                header_box_map_liq[col_name] = ocr_box[idx_header]
            else:
                header_box_map_liq[col_name] = None

        row_list = []
        extracted_position_data = []

        for yolo_box in sorted_det_boxes:
            yolo_box[0] = 0  # extend to left margin
            indices, _ = ocr_boxes_inside_yolo(yolo_box, ocr_box, threshold=0.8)
            result = [ocr_text[i] for i in indices]
            row_list.append({"text": result, "index": indices})

        skip_is_header_once = False
        for row in row_list:
            try:
                row_excel = {}
                row["text"] = [e.strip() for e in row["text"] if isinstance(e, str)]

                if not row["text"]:
                    continue

                if is_header(row["text"]):
                    if skip_is_header_once:
                        skip_is_header_once = False
                    else:
                        continue

                position_type_check = get_position_type(row)
                if position_type_check != "":
                    # detect if this is a pure section header (no numeric/currency content)
                    joined = " ".join(row.get("text", [])).strip()
                    joined_low = joined.lower()
                    has_currency = any(ccy.lower() in joined_low for ccy in currencies)
                    has_isin = "isin" in joined_low
                    has_percent = "%" in joined
                    has_decimal_or_longint = bool(re.search(r"\d+\.\d+", joined)) or bool(re.search(r"\d{3,}", joined))

                    if not (has_currency or has_isin or has_percent or has_decimal_or_longint):
                        # treat as header and allow next row through
                        self.position_type = position_type_check
                        skip_is_header_once = True
                        continue

                    self.position_type = position_type_check

                if self.position_type is None:
                    continue

                # -------------------------
                # Liquidity - Accounts
                # -------------------------
                if self.position_type == "Liquidity - Accounts":
                    row_json = {}

                    for col_name in liquidity_account_columns:
                        idx_header = header_idx_map_liq.get(col_name)
                        col_name_box = header_box_map_liq.get(col_name)

                        if idx_header is None or col_name_box is None:
                            row_json[col_name] = []
                            continue

                        ocr_box_of_current_row = [ocr_box[i] for i in row["index"]]
                        ocr_text_of_current_row = [ocr_text[i] for i in row["index"]]

                        aligned_indices = boxes_aligned_in_column_idx(
                            col_name_box,
                            ocr_box_of_current_row,
                            min_overlap_ratio=0.2,
                            center_within=False
                        )
                        row_json[col_name] = [ocr_text_of_current_row[i] for i in aligned_indices]

                    if len(row_json.get("By investment category", [])) == 0:
                        continue

                    if self.position_type in row_json["By investment category"]:
                        row_json["By investment category"].remove(self.position_type)

                    row_type = get_liquidity_row_type(row_json)
                    if row_type == "subtotal":
                        continue

                    currency = get_currency_liquidity_account(row_json)
                    account_no = row_json["Description"][-1] if row_json.get("Description") else ""
                    amount = get_liquidity_amount(row_json)

                    # ✅ format amount output
                    amount_out = self._format_number_output(amount)

                    row_excel["Portfolio No."] = self.portfolio_no or ""
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = account_no
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount_out
                    row_excel["Security ID"] = ""

                    # Derive a security name from Description for liquidity accounts.
                    desc_lines = row_json.get("Description", [])
                    security_name = ""
                    if desc_lines:
                        last = desc_lines[-1].strip()
                        looks_like_account_or_date = False
                        if is_account_no_like(last):
                            looks_like_account_or_date = True
                        if re.search(r"\b\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}\b", last):
                            looks_like_account_or_date = True

                        if looks_like_account_or_date and len(desc_lines) >= 2:
                            candidate_lines = desc_lines[:-1]
                        else:
                            candidate_lines = desc_lines

                        joined = " ".join([re.sub(r"\s+", " ", l).strip() for l in candidate_lines if l])
                        joined = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", joined)
                        joined = re.sub(r"\b(as of|as at|dated)\b.*", "", joined, flags=re.IGNORECASE)
                        joined = re.sub(r"\b\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}\b", "", joined)
                        joined = re.sub(r"\s+", " ", joined).strip()
                        security_name = joined

                    row_excel["Security name"] = security_name
                    row_excel["Cost price"] = ""
                    row_excel["Market price"] = ""
                    row_excel["Market value"] = ""
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = self.valuation_date or ""

                    extracted_position_data.append(row_excel)

                # -------------------------
                # Normal Position tables
                # -------------------------
                else:
                    row_json = {}

                    for col_name in position_columns:
                        idx_header = header_idx_map.get(col_name)
                        col_name_box = header_box_map.get(col_name)

                        if idx_header is None or col_name_box is None:
                            row_json[col_name] = []
                            continue

                        ocr_box_of_current_row = [ocr_box[i] for i in row["index"]]
                        ocr_text_of_current_row = [ocr_text[i] for i in row["index"]]

                        aligned_indices = boxes_aligned_in_column_idx(
                            col_name_box,
                            ocr_box_of_current_row,
                            min_overlap_ratio=0.2,
                            center_within=False
                        )
                        row_json[col_name] = [ocr_text_of_current_row[i] for i in aligned_indices]

                    row_type = get_row_type(row_json)
                    if row_type in ("subtotal", "empty"):
                        continue

                    currency = get_currency_position(row_json)
                    isin = get_isin_position(row_json)

                    amount = get_position_amount(row_json, self.position_type)
                    security_name_raw = get_security_name(row_json, self.position_type)

                    extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)
                    if extracted_qty is not None:
                        security_name = cleaned_name
                    else:
                        security_name = security_name_raw

                    security_name = re.sub(r"\s+", " ", (security_name or "")).strip()

                    if security_name:
                        security_name = security_name.strip()
                        security_name = re.sub(r"^[\(\)\s]+|[\(\)\s]+$", "", security_name)
                        security_name = re.sub(r"^[\d\s,\.oO]+\s+", "", security_name)
                        try:
                            if is_header(security_name):
                                security_name = ""
                        except Exception:
                            pass
                        security_name = security_name.strip()

                    try:
                        if amount == "" or amount is None:
                            extracted_qty_pos, _cleaned_name_pos = split_leading_quantity_position(security_name_raw)
                            if extracted_qty_pos is not None:
                                amount = extracted_qty_pos
                    except Exception:
                        pass

                    cost_price = get_position_cost_price(row_json, self.position_type)
                    market_price = get_market_price(row_json, self.position_type)
                    market_value = get_market_value(row_json, self.position_type)

                    # ✅ format numeric outputs (ONLY output formatting, no logic change)
                    amount_out = self._format_number_output(amount)
                    cost_price_out = self._format_number_output(cost_price)
                    market_price_out = self._format_number_output(market_price)
                    market_value_out = self._format_number_output(market_value)

                    row_excel["Portfolio No."] = self.portfolio_no or ""
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = ""
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount_out
                    row_excel["Security ID"] = isin
                    row_excel["Security name"] = security_name
                    row_excel["Cost price"] = cost_price_out
                    row_excel["Market price"] = market_price_out
                    row_excel["Market value"] = market_value_out
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = self.valuation_date or ""

                    extracted_position_data.append(row_excel)

            except Exception as e:
                print(f"[WARN] Position row skipped due to error: {e}")
                continue

        return extracted_position_data
