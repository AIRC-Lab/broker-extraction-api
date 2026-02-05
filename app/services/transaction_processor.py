from typing import List, Any
from PIL import Image
from app.utils import *
from app.utils import _parse_signed_number_string
import math
import numpy as np
import re


class TransactionProcessor:
    """
    Processor extract Transaction info (trade / fx_tf / other) từ OCR + YOLO.

    Ý tưởng:
    - YOLO detect row bands
    - OCR tokens + boxes
    - map token vào cột dựa header (transaction_columns)
    - parse transaction type từ Booking text
    - validate mạnh để tránh noise
    - split ra 3 nhóm output:
        + trade_info (Buy/Sell)
        + fx_tf_info (FX Forward)
        + other_info (Call Deposit/Increase/New investment)
    """

    def __init__(self) -> None:
        # Metadata set từ tasks.py khi tìm được trang header
        self.client_name = None

    def process(
        self,
        yolo_model: Any,
        image: Image.Image,
        ocr_result: List[dict]
    ) -> dict:
        """
        Main extraction cho transaction pages.

        Output:
        {
          "trade_info": [...],
          "fx_tf_info": [...],
          "other_info": [...]
        }
        """

        # 1) YOLO detect row boxes
        detection_result = yolo_model.predict(image)[0].boxes.xyxy.tolist()
        ceil_det_box = [[math.ceil(x) for x in yolo_box] for yolo_box in detection_result]
        sorted_det_boxes = sorted(ceil_det_box, key=lambda box: box[1])

        # 2) OCR tokens + boxes
        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]

        # ---------------------------------------------------------
        # PRE-COMPUTE HEADER INDEX + HEADER BOX PER COLUMN
        # - tránh duplicate header text
        # - tăng ổn định mapping token->column
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
        # Page-level currency fallback:
        # - Một số trang transaction/other chỉ nói "Valued in SGD"
        # - Khi row không extract được currency -> dùng fallback này
        # ---------------------------------------------------------
        page_currency = ""
        try:
            full_page_text = " ".join([t for t in ocr_text if isinstance(t, str)])
            m = re.search(r"\bvalued\s+in\s+([A-Z]{3})\b", full_page_text, flags=re.IGNORECASE)
            if m:
                page_currency = (m.group(1) or "").strip().upper()
        except Exception:
            page_currency = ""

        # 3) Build row_list: mỗi YOLO row -> tokens nằm trong row
        row_list = []
        for yolo_box in sorted_det_boxes:
            try:
                # extend to left margin để không miss token sát trái
                yolo_box[0] = 0

                # threshold 0.8: token phải nằm phần lớn bên trong row box
                indices, _ = ocr_boxes_inside_yolo(yolo_box, ocr_box, threshold=0.8)
                result = [ocr_text[i] for i in indices]
                row_list.append({"text": result, "index": indices})
            except Exception:
                continue

        # Output groups
        trade_information = []
        fx_tf_information = []
        other_information = []

        # Cờ skip section header row
        skip_next_header = False

        # 4) Parse từng row
        for row in row_list:
            try:
                row["text"] = [e.strip() for e in row["text"] if isinstance(e, str)]
                if not row["text"]:
                    continue

                # Nếu row là header/section header -> skip
                if is_header(row["text"]):
                    skip_next_header = True
                    continue
                if skip_next_header:
                    skip_next_header = False

                row_json = {}

                # Map tokens trong row vào từng cột bằng header alignment
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
                        below_header_only=True,   # tránh match nhầm header trên cùng hàng
                    )
                    row_json[col_name] = [ocr_text_of_current_row[i] for i in aligned_indices]

                # ---------------------------------------------------------
                # HARD ROW VALIDATION:
                # - booking text phải có
                # - phải có trade_date hoặc settlement_date
                # => giảm noise rows bị YOLO/OCR bắt nhầm
                # ---------------------------------------------------------
                booking_text_join = " ".join(row_json.get("Booking text", [])).strip()
                trade_date, settlement_date = get_trade_settlement_date(row_json)

                if not booking_text_join:
                    continue
                if not trade_date and not settlement_date:
                    continue

                row_excel = {}

                # ---------------------------------------------------------
                # FIX (OTHER): detect Increase / New investment trước,
                # vì get_transaction_type() không map 2 case này
                # ---------------------------------------------------------
                booking_low = booking_text_join.lower()

                is_other_increase = False
                is_other_new_investment = False

                if "increase" in booking_low:
                    is_other_increase = True

                if ("new investment" in booking_low) or ("new invest" in booking_low) or ("new inv" in booking_low):
                    is_other_new_investment = True

                transaction_type = get_transaction_type(row_json)

                # =========================
                # CASE 1: Purchase / Sale -> Buy / Sell
                # =========================
                if transaction_type in ["Purchase", "Sale"]:

                    transaction_type_out = "Buy" if transaction_type == "Purchase" else "Sell"

                    isin = get_isin(row_json)
                    currency = get_currency(row_json)

                    # Build security name từ Custody account lines
                    custody_lines = row_json.get("Custody account", [])
                    security_name_raw = build_security_name_from_custody_account_lines(custody_lines)

                    # fallback nếu empty: lấy 1-2 dòng đầu "hợp lý" trong custody
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

                    # Nếu tên bắt đầu bằng qty -> tách qty ra và ưu tiên qty nếu thiếu
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

                    # net_consideration chỉ set khi có accrued_interest (theo logic bạn)
                    net_consideration = foreign_net_consideration if accrued_interest != "" else ""

                    # Validation để tránh junk rows bị tính là trade
                    if not isin:
                        continue
                    if quantity is None or quantity == "":
                        continue
                    if not account_no:
                        continue

                    # Fill schema trade.xlsx
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
                # CASE 2: UBS Call Deposit / Increase / New investment -> OTHER
                # =========================
                elif (transaction_type == "UBS Call Deposit") or is_other_increase or is_other_new_investment:
                    isin = get_isin(row_json)

                    # Currency extraction cho OTHER rows:
                    # 1) get_currency(row_json)
                    # 2) scan row text tìm currency code
                    # 3) fallback page_currency ("Valued in XXX")
                    row_currency = ""
                    try:
                        row_currency = get_currency(row_json) or ""
                    except Exception:
                        row_currency = ""

                    if not row_currency:
                        try:
                            row_text_all = " ".join(row.get("text", []))
                            for ccy in currencies:
                                if re.search(rf"\b{re.escape(ccy)}\b", row_text_all):
                                    row_currency = ccy
                                    break
                        except Exception:
                            pass

                    if not row_currency and page_currency:
                        row_currency = page_currency

                    # set transaction type output cho Increase / New investment
                    transaction_type_out = transaction_type
                    if is_other_increase and transaction_type != "UBS Call Deposit":
                        transaction_type_out = "Increase"
                    if is_other_new_investment and transaction_type != "UBS Call Deposit":
                        transaction_type_out = "New investment"

                    # Fill schema other.xlsx
                    row_excel["Client name"] = self.client_name or ""
                    
                    booking_text_val = row_json["Booking text"][0].strip() if row_json.get("Booking text") else ""

                    if transaction_type_out == "Increase":
                        # For Increase: Description = content of Description column, Type = Short Type
                        desc_val = row_json.get("Description", [])
                        desc_str = desc_val[0].strip() if desc_val else ""
                        row_excel["Description"] = desc_str
                        row_excel["Transaction type"] = transaction_type_out
                    else:
                        # For others: Description = Short Type, Type = Booking Text
                        row_excel["Description"] = transaction_type_out
                        row_excel["Transaction type"] = booking_text_val

                    row_excel["Securities ID"] = isin
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Currency"] = row_currency
                    # Extract Quantity from "Number/Amount" and strip currency if present
                    qty_raw_list = row_json.get("Number/Amount", [])
                    qty_raw = qty_raw_list[0].strip() if qty_raw_list else ""

                    # Strict extraction: find the first sequence that looks like a number
                    try:
                        # Updated regex to allow spaces as thousands separators
                        # Matches: optional sign, digits/commas/spaces, optional decimal part
                        match_num = re.search(r"[\-\+]?[\d, ]+(?:\.\d+)?", qty_raw)
                        clean_qty = ""
                        if match_num:
                            # Parse the candidate string
                            parsed_val = _parse_signed_number_string(match_num.group(0))
                            if parsed_val != "":
                                clean_qty = str(parsed_val)
                    except Exception:
                        clean_qty = ""

                    row_excel["Quantity"] = clean_qty
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
                # CASE 3: FX Forward / FX Spot -> fx_tf.xlsx
                # =========================
                elif transaction_type in ["FX Forward", "FX Spot"]:
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
                    # Unknown type -> skip row
                    continue

            except Exception:
                # Skip row lỗi
                continue

        return {
            "trade_info": trade_information,
            "fx_tf_info": fx_tf_information,
            "other_info": other_information
        }
