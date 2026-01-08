from typing import List, Any

from PIL import Image
from app.utils import *

import math
import numpy as np
import re


class TransactionProcessor:
    """A processor for extracting and refining Transactional information
    from OCR results using a YOLO object detection model."""

    def __init__(self) -> None:
        pass

    def process(
        self,
        yolo_model: Any,
        image: Image.Image,
        ocr_result: List[dict]
    ) -> dict:

        detection_result = yolo_model.predict(image)[0].boxes.xyxy.tolist()
        ceil_det_box = [[math.ceil(x) for x in yolo_box] for yolo_box in detection_result]
        sorted_det_boxes = sorted(ceil_det_box, key=lambda box: box[1])

        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]

        row_list = []
        for yolo_box in sorted_det_boxes:
            indices, _ = ocr_boxes_inside_yolo(yolo_box, ocr_box, threshold=0.9)
            result = [ocr_text[i] for i in indices]
            row_list.append({"text": result, "index": indices})

        trade_information = []
        fx_tf_information = []
        other_information = []

        for row in row_list:
            try:
                row["text"] = [e.strip() for e in row["text"]]
                if is_header(row["text"]):
                    continue

                row_json = {}
                for col_name in transaction_columns:
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

                row_excel = {}
                transaction_type = get_transaction_type(row_json)

                # =========================
                # Purchase / Sale (Trade)
                # =========================
                if transaction_type in ["Purchase", "Sale"]:
                    isin = get_isin(row_json)
                    trade_date, settlement_date = get_trade_settlement_date(row_json)
                    currency = get_currency(row_json)

                    custody_lines = row_json.get("Custody account", [])
                    security_name_raw = build_security_name_from_custody_account_lines(custody_lines)
                    if not security_name_raw:
                        security_name_raw = " ".join(custody_lines).strip()

                    quantity = get_quantity(row_json)

                    # ✅ ALWAYS split if leading looks like quantity
                    extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)
                    if extracted_qty is not None:
                        security_name = re.sub(r"\s+", " ", cleaned_name).strip()
                        if quantity is None or quantity == "" or quantity == 0:
                            quantity = extracted_qty
                    else:
                        security_name = remove_start_number(security_name_raw)
                        security_name = re.sub(r"\s+", " ", security_name).strip()

                    account_no = get_account_no(row_json)
                    foreign_unit_price = get_foreign_unit_price(row_json, transaction_type)
                    foreign_gross_consideration, foreign_net_consideration, accrued_interest = get_foreign_gross_net_consideration(
                        row_json, transaction_type
                    )
                    net_consideration = foreign_net_consideration if accrued_interest != "" else ""

                    row_excel["Client name"] = "GINKGO TREE GLOBAL ALLOCATION FUND"
                    row_excel["Name/ Security"] = security_name
                    row_excel["Securities ID"] = isin
                    row_excel["Transaction type"] = transaction_type
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Currency"] = currency
                    row_excel["Quantity"] = quantity
                    row_excel["Account no."] = account_no
                    row_excel["Foreign Unit Price"] = foreign_unit_price
                    row_excel["Foreign Gross consideration"] = foreign_gross_consideration
                    row_excel["Foreign Net consideration"] = foreign_net_consideration
                    row_excel["Net consideration"] = net_consideration
                    row_excel["Commission fee (Base)"] = ""
                    row_excel["Accrued interest"] = accrued_interest
                    row_excel["Foreign Transaction Fee"] = ""

                    trade_information.append(row_excel)

                # =========================
                # UBS Call Deposit
                # =========================
                elif transaction_type == "UBS Call Deposit":
                    isin = get_isin(row_json)
                    trade_date, settlement_date = get_trade_settlement_date(row_json)

                    row_excel["Client name"] = "GINKGO TREE GLOBAL ALLOCATION FUND"
                    row_excel["Description"] = row_json["Booking text"][0].strip() if row_json.get("Booking text") else ""
                    row_excel["Securities ID"] = isin
                    row_excel["Transaction type"] = transaction_type
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Currency"] = ""
                    row_excel["Quantity"] = ""
                    row_excel["Foreign Unit Price/ Interest rate"] = ""

                    foreign_gross_consideration, _, accrued_interest = get_foreign_gross_net_consideration(
                        row_json, transaction_type
                    )
                    row_excel["Foreign Gross Amount/Interest"] = foreign_gross_consideration
                    row_excel["Tax rate (%)"] = ""
                    row_excel["Foreign Net Amount"] = row_excel["Foreign Gross Amount/Interest"]
                    row_excel["Payment mode"] = ""
                    row_excel["Account no."] = get_account_no(row_json)
                    row_excel["Exrate to GST"] = ""
                    row_excel["Amount (SGD)"] = ""

                    other_information.append(row_excel)

                # =========================
                # FX Forward
                # =========================
                elif transaction_type == "FX Forward":
                    trade_date, settlement_date = get_trade_settlement_date(row_json)

                    row_excel["Client name"] = "GINKGO TREE GLOBAL ALLOCATION FUND"
                    row_excel["Transaction type"] = transaction_type
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Rate"] = row_json["Cost/Purchase price"][0].strip() if row_json.get("Cost/Purchase price") else ""

                    currency_buy, amount_buy = get_currency_amount_buy(row_json)
                    currency_sell, amount_sell = get_currency_amount_sell(row_json)
                    account_buy, account_sell = get_account_no_buy_sell(row_json)

                    row_excel["Currency Buy"] = currency_buy
                    row_excel["Amount Buy"] = amount_buy
                    row_excel["Currency Sell"] = currency_sell
                    row_excel["Amount Sell"] = amount_sell
                    row_excel["Account no. Buy"] = account_buy
                    row_excel["Account no. Sell"] = account_sell

                    fx_tf_information.append(row_excel)

            except:
                continue

        return {
            "trade_info": trade_information,
            "fx_tf_info": fx_tf_information,
            "other_info": other_information
        }
