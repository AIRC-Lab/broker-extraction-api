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
        self.client_name = None

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

        # ---------------------------------------------------------
        # ✅ PRE-COMPUTE HEADER INDEX + HEADER BOX PER COLUMN
        # To avoid duplicate header text and ensure consistent columns
        # ---------------------------------------------------------
        header_idx_map = {}
        header_box_map = {}
        for col_name in transaction_columns:
            idx_header = get_index_by_name(col_name, ocr_text)
            header_idx_map[col_name] = idx_header
            if idx_header is not None:
                header_box_map[col_name] = ocr_box[idx_header]
            else:
                header_box_map[col_name] = None

        # ---------------------------------------------------------
        # ✅ FIX (OTHER): page-level currency fallback, e.g. "Valued in SGD"
        # Only used when row-level currency is missing.
        # ---------------------------------------------------------
        page_currency = ""
        try:
            full_page_text = " ".join([t for t in ocr_text if isinstance(t, str)])
            m = re.search(r"\bvalued\s+in\s+([A-Z]{3})\b", full_page_text, flags=re.IGNORECASE)
            if m:
                page_currency = (m.group(1) or "").strip().upper()
        except Exception:
            page_currency = ""

        row_list = []
        for yolo_box in sorted_det_boxes:
            try:
                # ✅ Extend to left margin (same as PositionProcessor)
                yolo_box[0] = 0

                # ✅ slightly relax threshold to avoid missing OCR boxes in row
                indices, _ = ocr_boxes_inside_yolo(yolo_box, ocr_box, threshold=0.8)
                result = [ocr_text[i] for i in indices]
                row_list.append({"text": result, "index": indices})
            except Exception:
                continue

        trade_information = []
        fx_tf_information = []
        other_information = []
        # When a section header is encountered, skip that header row
        # but allow the very next row (first data row) to be processed.
        skip_next_header = False

        for row in row_list:
            try:
                row["text"] = [e.strip() for e in row["text"] if isinstance(e, str)]
                if not row["text"]:
                    continue

                # If this row looks like a section header, skip it
                # and allow the following row to pass through.
                if is_header(row["text"]):
                    skip_next_header = True
                    continue
                if skip_next_header:
                    skip_next_header = False

                row_json = {}

                # Build row_json by aligning row boxes under each header column
                for col_name in transaction_columns:
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
                        center_within=False,
                        below_header_only=True,
                    )
                    row_json[col_name] = [ocr_text_of_current_row[i] for i in aligned_indices]

                # ---------------------------------------------------------
                # ✅ HARD ROW VALIDATION (reduce false positives / noisy rows)
                # ---------------------------------------------------------
                booking_text_join = " ".join(row_json.get("Booking text", [])).strip()
                trade_date, settlement_date = get_trade_settlement_date(row_json)

                # If not a real transaction row, skip
                if not booking_text_join:
                    continue
                if not trade_date and not settlement_date:
                    continue

                row_excel = {}

                # ---------------------------------------------------------
                # ✅ FIX (OTHER): recognize Increase / New investment
                # before calling get_transaction_type(), because your
                # get_transaction_type() does not map these -> they got skipped.
                # ---------------------------------------------------------
                booking_low = booking_text_join.lower()

                is_other_increase = False
                is_other_new_investment = False

                # robust contains checks (OCR variations)
                if "increase" in booking_low:
                    is_other_increase = True

                if ("new investment" in booking_low) or ("new invest" in booking_low) or ("new inv" in booking_low):
                    is_other_new_investment = True

                transaction_type = get_transaction_type(row_json)

                # =========================
                # Purchase / Sale → Buy / Sell
                # =========================
                if transaction_type in ["Purchase", "Sale"]:

                    transaction_type_out = "Buy" if transaction_type == "Purchase" else "Sell"

                    isin = get_isin(row_json)
                    currency = get_currency(row_json)

                    custody_lines = row_json.get("Custody account", [])
                    security_name_raw = build_security_name_from_custody_account_lines(custody_lines)

                    # fallback if empty
                    if not security_name_raw:
                        fallback_lines = []
                        for ln in custody_lines:
                            if not ln:
                                continue
                            t = re.sub(r"\s+", " ", str(ln)).strip()
                            if not t:
                                continue
                            low = t.lower()
                            if low.startswith("you bought") or low.startswith("you sold"):
                                continue
                            if "isin" in low:
                                continue
                            if is_account_no_like(t):
                                break
                            fallback_lines.append(t)
                            if len(fallback_lines) >= 2:
                                break
                        security_name_raw = " ".join(fallback_lines).strip()

                    quantity = get_quantity(row_json)

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

                    foreign_gross_consideration, foreign_net_consideration, accrued_interest = \
                        get_foreign_gross_net_consideration(row_json, transaction_type)

                    net_consideration = foreign_net_consideration if accrued_interest != "" else ""

                    # ✅ more validation to avoid junk rows counted as trades
                    if not isin:
                        continue
                    if quantity is None or quantity == "":
                        continue
                    if not account_no:
                        continue

                    row_excel["Client name"] = self.client_name or ""
                    row_excel["Name/ Security"] = security_name
                    row_excel["Securities ID"] = isin
                    row_excel["Transaction type"] = transaction_type_out
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
                # UBS Call Deposit (OTHER) + Increase + New investment
                # =========================
                elif (transaction_type == "UBS Call Deposit") or is_other_increase or is_other_new_investment:
                    isin = get_isin(row_json)

                    # ---------------------------------------------------------
                    # ✅ FIX (OTHER): currency extraction for OTHER rows
                    # priority:
                    #   1) get_currency(row_json)
                    #   2) scan row text for any 3-letter currency
                    #   3) page_currency ("Valued in XXX")
                    # ---------------------------------------------------------
                    row_currency = ""
                    try:
                        row_currency = get_currency(row_json) or ""
                    except Exception:
                        row_currency = ""

                    if not row_currency:
                        try:
                            row_text_all = " ".join(row.get("text", []))
                            # find first currency code appears in row
                            for ccy in currencies:
                                if re.search(rf"\b{re.escape(ccy)}\b", row_text_all):
                                    row_currency = ccy
                                    break
                        except Exception:
                            pass

                    if not row_currency and page_currency:
                        row_currency = page_currency

                    # choose output transaction type for these two "other" types
                    transaction_type_out = transaction_type
                    if is_other_increase and transaction_type != "UBS Call Deposit":
                        transaction_type_out = "Increase"
                    if is_other_new_investment and transaction_type != "UBS Call Deposit":
                        transaction_type_out = "New investment"

                    row_excel["Client name"] = self.client_name or ""
                    row_excel["Description"] = row_json["Booking text"][0].strip() if row_json.get("Booking text") else ""
                    row_excel["Securities ID"] = isin
                    row_excel["Transaction type"] = transaction_type_out
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Currency"] = row_currency
                    row_excel["Quantity"] = ""
                    row_excel["Foreign Unit Price/ Interest rate"] = ""

                    foreign_gross_consideration, foreign_net_consideration, accrued_interest = \
                        get_foreign_gross_net_consideration_other(row_json)

                    row_excel["Foreign Gross Amount/Interest"] = foreign_gross_consideration
                    row_excel["Tax rate (%)"] = ""
                    row_excel["Foreign Net Amount"] = foreign_net_consideration
                    row_excel["Payment mode"] = ""
                    row_excel["Account no."] = get_account_no(row_json)
                    row_excel["Exrate to GST"] = ""
                    row_excel["Amount (SGD)"] = ""

                    other_information.append(row_excel)

                # =========================
                # FX Forward
                # =========================
                elif transaction_type == "FX Forward":
                    rate = get_fx_forward_rate(row_json)
                    if rate == "":
                        continue

                    row_excel["Client name"] = self.client_name or ""
                    row_excel["Transaction type"] = transaction_type
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Rate"] = rate

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

                else:
                    # unknown type -> skip
                    continue

            except Exception:
                continue

        return {
            "trade_info": trade_information,
            "fx_tf_info": fx_tf_information,
            "other_info": other_information
        }
