from typing import List, Any

from PIL import Image
from app.utils import *

import math
import numpy as np


class PositionProcessor:
    """A processor for extracting and refining positional information
    from OCR results using a YOLO object detection model."""

    def __init__(self) -> None:
        self.position_type = None

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

        row_list = []
        extracted_position_data = []

        for yolo_box in sorted_det_boxes:
            yolo_box[0] = 0  # extend to left margin
            indices, _ = ocr_boxes_inside_yolo(yolo_box, ocr_box, threshold=0.8)
            result = [ocr_text[i] for i in indices]
            row_list.append({"text": result, "index": indices})

        for row in row_list:
            try:
                row_excel = {}
                row["text"] = [e.strip() for e in row["text"]]

                if is_header(row["text"]):
                    continue

                position_type_check = get_position_type(row)
                if position_type_check != "":
                    self.position_type = position_type_check

                if self.position_type is None:
                    continue

                # -------------------------
                # Liquidity - Accounts
                # -------------------------
                if self.position_type == "Liquidity - Accounts":
                    row_json = {}

                    for col_name in liquidity_account_columns:
                        idx_header = get_index_by_name(col_name, ocr_text)
                        if idx_header is None:
                            row_json[col_name] = []
                            continue

                        col_name_box = ocr_box[idx_header]
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

                    row_excel["Portfolio No."] = "546-880515-01"
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = account_no
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount
                    row_excel["Security ID"] = ""
                    row_excel["Security name"] = ""
                    row_excel["Cost price"] = ""
                    row_excel["Market price"] = ""
                    row_excel["Market value"] = ""
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = ""

                    extracted_position_data.append(row_excel)

                # -------------------------
                # Normal Position tables
                # -------------------------
                else:
                    row_json = {}

                    for col_name in position_columns:
                        idx_header = get_index_by_name(col_name, ocr_text)
                        if idx_header is None:
                            row_json[col_name] = []
                            continue

                        col_name_box = ocr_box[idx_header]
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

                    # existing quantity logic
                    amount = get_position_amount(row_json, self.position_type)

                    # -------------------------------------------------------
                    # FIX: Security name must NOT contain leading quantity
                    # Example bad: "100 000 Toyota Motor Credit Corp ..."
                    # Keep pdf-like name, remove only true leading quantity.
                    # -------------------------------------------------------
                    security_name_raw = get_security_name(row_json, self.position_type)

                    extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)
                    if extracted_qty is not None:
                        # IMPORTANT: we only use this to CLEAN NAME,
                        # we do NOT overwrite Quantity/ Amount here.
                        security_name = cleaned_name
                    else:
                        security_name = security_name_raw

                    security_name = re.sub(r"\s+", " ", (security_name or "")).strip()

                    # =========================================================
                    # ✅ FIX ONLY: Fill missing Quantity/Amount from Security line
                    # Keep name logic unchanged, only fill 'amount' when missing.
                    # Use position-specific splitter (handles OCR "o/O" -> 0 etc.)
                    # =========================================================
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

                    row_excel["Portfolio No."] = "546-880515-01"
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
                    row_excel["Valuation date"] = "03/31/25"

                    extracted_position_data.append(row_excel)

            except Exception:
                continue

        return extracted_position_data
