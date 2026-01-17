from typing import List, Any
from PIL import Image
from app.utils import *
import math
import numpy as np
import re


class PositionProcessor:
    """A processor for extracting and refining positional information
    from OCR results using a YOLO object detection model."""

    def __init__(self) -> None:
        self.position_type = None
        self.portfolio_no = None

        # ✅ FIX: was missing -> caused AttributeError -> skipped ALL rows
        self.valuation_date = ""

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

                    row_excel["Portfolio No."] = self.portfolio_no or ""
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = account_no
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount
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

                    row_excel["Portfolio No."] = self.portfolio_no or ""
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = ""
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount
                    row_excel["Security ID"] = isin
                    row_excel["Security name"] = security_name
                    row_excel["Cost price"] = cost_price
                    row_excel["Market price"] = market_price
                    row_excel["Market value"] = market_value
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = self.valuation_date or ""

                    extracted_position_data.append(row_excel)

            except Exception as e:
                print(f"[WARN] Position row skipped due to error: {e}")
                continue

        return extracted_position_data
