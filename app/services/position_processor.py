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

        if isinstance(v, Decimal):
            return format(v, "f")

        if isinstance(v, (int, float)):
            s = str(v).strip()
        else:
            s = str(v).strip()

        if not s:
            return ""

        s = s.replace("−", "-").replace("–", "-")

        s_clean = re.sub(r"[^0-9\-\+\s,\.()]", "", s).strip()
        if not s_clean:
            return ""

        neg_by_paren = False
        if "(" in s_clean and ")" in s_clean:
            neg_by_paren = True

        s_no_paren = s_clean.replace("(", "").replace(")", "").strip()
        if not s_no_paren:
            return ""

        dot_pos = s_no_paren.rfind(".")
        comma_pos = s_no_paren.rfind(",")

        decimal_sep = None
        if dot_pos != -1 and comma_pos != -1:
            decimal_sep = "," if comma_pos > dot_pos else "."
        elif comma_pos != -1 and dot_pos == -1:
            if re.search(r",\d{3}(?:[^\d]|$)", s_no_paren):
                decimal_sep = None
            else:
                decimal_sep = ","
        else:
            decimal_sep = "."

        normalized = s_no_paren.replace(" ", "")

        if decimal_sep == ",":
            normalized = normalized.replace(".", "")
            normalized = normalized.replace(",", ".")
        else:
            normalized = normalized.replace(",", "")

        normalized = re.sub(r"[^0-9\-\+\.]", "", normalized).strip()
        if not normalized:
            return ""

        try:
            dv = Decimal(normalized)
            if neg_by_paren and dv > 0:
                normalized = "-" + normalized.lstrip("+").lstrip("-")
            if normalized.endswith("."):
                normalized = normalized[:-1]
            return normalized
        except Exception:
            return ""

    def _looks_like_section_header_only(self, row_text_tokens: List[str]) -> bool:
        """
        A row is likely a pure section header when it has no numeric/currency/ISIN content.
        """
        joined = " ".join(row_text_tokens or []).strip()
        if not joined:
            return False

        joined_low = joined.lower()
        has_currency = any(ccy.lower() in joined_low for ccy in currencies)
        has_isin = "isin" in joined_low
        has_percent = "%" in joined
        has_decimal_or_longint = bool(re.search(r"\d+\.\d+", joined)) or bool(re.search(r"\d{3,}", joined))

        return not (has_currency or has_isin or has_percent or has_decimal_or_longint)

    def _detect_position_type_fallback(self, row_text_tokens: List[str]) -> str:
        """
        Fallback detection for types that OCR may truncate / vary,
        or types that are not covered by utils.get_position_type().
        """
        joined = " ".join(row_text_tokens or []).strip()
        low = joined.lower()

        # ✅ Hedge funds should be treated as a Type header (not security name)
        # Keep it strict-ish to avoid false positives.
        if re.fullmatch(r"\s*hedge\s+funds\s*", low):
            return "Hedge funds"

        # ✅ Missing type: Liquidity - FX swap & forward contracts (OCR variations)
        # Accept common truncations: "contrac", "contracts", etc.
        if ("liquidity" in low) and ("fx" in low) and ("swap" in low) and ("forward" in low):
            return "Liquidity - FX swap & forward contracts"

        # ✅ Money market investments (handle OCR variations)
        if ("liquidity" in low) and ("money" in low) and ("market" in low) and ("invest" in low):
            return "Liquidity - Money market investments"

        return ""

    def _row_is_effectively_empty_position_row(
        self,
        *,
        security_name: str,
        isin: str,
        currency: str,
        amount_out: str,
        cost_price_out: str,
        market_price_out: str,
        market_value_out: str
    ) -> bool:
        """
        Remove redundant/blank rows (e.g. duplicated type line like 'Liquidity - Money market investments'
        that shows up as an empty row).
        """
        def _nz(s):
            return (str(s).strip() if s is not None else "")

        if _nz(security_name) or _nz(isin) or _nz(currency):
            return False
        if _nz(amount_out) or _nz(cost_price_out) or _nz(market_price_out) or _nz(market_value_out):
            return False
        return True

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

                # header rows (table headers etc.)
                if is_header(row["text"]):
                    if skip_is_header_once:
                        skip_is_header_once = False
                    else:
                        continue

                # ---------------------------------------------------------
                # ✅ TYPE DETECTION
                # - use utils.get_position_type(row) (existing)
                # - plus fallback for:
                #   * Hedge funds (treat as Type header)
                #   * Liquidity - FX swap & forward contracts (OCR variations)
                #   * Money market investments (OCR variations)
                # ---------------------------------------------------------
                position_type_check = get_position_type(row)
                if not position_type_check:
                    position_type_check = self._detect_position_type_fallback(row.get("text", []))

                if position_type_check != "":
                    # detect pure section header (no numeric/currency content)
                    if self._looks_like_section_header_only(row.get("text", [])):
                        self.position_type = position_type_check
                        skip_is_header_once = True
                        continue
                    self.position_type = position_type_check

                # If we still have no position type, we cannot parse the row
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
                    amount_out = self._format_number_output(amount)

                    row_excel["Portfolio No."] = self.portfolio_no or ""
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = account_no
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount_out
                    row_excel["Security ID"] = ""

                    # Security name from Description (keep your current logic)
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
                    # ✅ If this row is a standalone "Hedge funds" header line, do not parse as a position row.
                    # (prevents "Hedge funds" being wrongly assigned as Security name)
                    if self.position_type == "Hedge funds" and self._looks_like_section_header_only(row.get("text", [])):
                        skip_is_header_once = True
                        continue

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

                    # If amount missing, try quantity split fallback (kept)
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

                    amount_out = self._format_number_output(amount)
                    cost_price_out = self._format_number_output(cost_price)
                    market_price_out = self._format_number_output(market_price)
                    market_value_out = self._format_number_output(market_value)

                    # ---------------------------------------------------------
                    # ✅ FIX: remove duplicated/blank "Liquidity - Money market investments" row
                    # If the parsed row has no real data, skip it.
                    # (also helps for any duplicated type line that leaks into table rows)
                    # ---------------------------------------------------------
                    if self._row_is_effectively_empty_position_row(
                        security_name=security_name,
                        isin=isin,
                        currency=currency,
                        amount_out=amount_out,
                        cost_price_out=cost_price_out,
                        market_price_out=market_price_out,
                        market_value_out=market_value_out
                    ):
                        continue

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
