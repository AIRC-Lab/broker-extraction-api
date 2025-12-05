from typing import List, Tuple
from datetime import datetime
import re

Box = Tuple[float, float, float, float]  # (x1, y1, x2, y2)

def box_contains(outer: Box, inner: Box, tol: float = 0.0) -> bool:
    """
    Check if the 'inner' box is fully inside the 'outer' box.
    tol: tolerance in pixels (positive = looser, negative = stricter)
    """
    ox1, oy1, ox2, oy2 = normalize_box(outer)
    ix1, iy1, ix2, iy2 = normalize_box(inner)
    return (ix1 >= ox1 - tol and
            iy1 >= oy1 - tol and
            ix2 <= ox2 + tol and
            iy2 <= oy2 + tol)

def ocr_boxes_inside_yolo(yolo_box: Box, ocr_boxes: List[Box], tol: float = 0.0):
    """
    Return:
      - indices: list of indices of OCR boxes inside the YOLO box
      - boxes:   the actual OCR boxes inside
    """
    indices = []
    kept = []
    for i, b in enumerate(ocr_boxes):
        if box_contains(yolo_box, b, tol=tol):
            indices.append(i)
            kept.append(b)
    return indices, kept

def classify_page_type(text: str) -> str:
    """
    Classify the page type based on key phrases found in the input text.

    Args:
        text (str): The page text to analyze.

    Returns:
        str: One of the following types:
            - "position"
            - "liquidity - accounts"
            - "transaction"
            - "other"
    """
    text = text or ""
    
    if all(keyword in text for keyword in ("Detailed positions", "Last purchase")):
        return "position"
    elif all(keyword in text for keyword in ("Liquidity - Accounts", "Valued in")):
        return "liquidity - accounts"
    elif all(keyword in text for keyword in ("Transaction list", "Valued in")):
        return "transaction"
    
    return "other"

def normalize_box(box: Box) -> Box:
    """Ensure (x1, y1) is top-left and (x2, y2) is bottom-right."""
    x1, y1, x2, y2 = box
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def box_contains(outer: Box, inner: Box, threshold: float = 0.8) -> bool:
    """
    Determine if the overlap (IoU) between the outer and inner boxes 
    is greater than a specified threshold.

    Args:
        outer (Box): The outer bounding box (x1, y1, x2, y2).
        inner (Box): The inner bounding box (x1, y1, x2, y2).
        threshold (float): Minimum IoU threshold for containment (default=0.5).

    Returns:
        bool: True if IoU(inner, outer) > threshold, else False.
    """

    def iou(boxA: Box, boxB: Box) -> float:
        # Calculate intersection
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        inter_width = max(0, xB - xA)
        inter_height = max(0, yB - yA)
        intersection = inter_width * inter_height

        # Calculate union
        areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        union = areaB

        if union == 0:
            return 0.0
        return intersection / union
    return iou(outer, inner) > threshold

def ocr_boxes_inside_yolo(yolo_box: Box, ocr_boxes: List[Box], threshold: float = 0.8):
    """
    Return:
      - indices: list of indices of OCR boxes inside the YOLO box
      - boxes:   the actual OCR boxes inside
    """
    indices = []
    kept = []
    for i, b in enumerate(ocr_boxes):
        if box_contains(yolo_box, b, threshold):
            indices.append(i)
            kept.append(b)
    return indices, kept

def classify_page_type(text: str) -> str:
    """
    Classify the page type based on key phrases found in the input text.

    Args:
        text (str): The page text to analyze.

    Returns:
        str: One of the following types:
            - "position"
            - "liquidity - accounts"
            - "transaction"
            - "other"
    """
    text = text or ""
    
    if all(keyword in text for keyword in ("Detailed positions", "Last purchase")):
        return "position"
    elif all(keyword in text for keyword in ("Liquidity - Accounts", "Valued in")):
        return "position"
    elif all(keyword in text for keyword in ("Transaction list", "Valued in")):
        return "transaction"
    
    return "other"

transaction_columns = [
    "Trade date",
    "Booking text",
    "Transaction Tax",
    "Custody account",
    "Cost/Purchase price",
    "Transaction price",
    "Transaction gain",
    "Transaction value"
]

position_columns = [
    "By investment category",
    "Description",
    "Duration",
    "Cost price",
    "Market price",
    "Market gain",
    "Market value"
]

liquidity_account_columns = [
    "By investment category",
    "Description"
]
def normalize_box(b: Box) -> Box:
    x1, y1, x2, y2 = b
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

def x_overlap(a: Box, b: Box) -> float:
    ax1, _, ax2, _ = normalize_box(a)
    bx1, _, bx2, _ = normalize_box(b)
    return max(0.0, min(ax2, bx2) - max(ax1, bx1))

def width(b: Box) -> float:
    x1, _, x2, _ = normalize_box(b)
    return max(0.0, x2 - x1)

def center_x(b: Box) -> float:
    x1, _, x2, _ = normalize_box(b)
    return (x1 + x2) / 2.0

def boxes_aligned_in_column_idx(
    header_box: Box,
    nboxes: List[Box],
    *,
    min_overlap_ratio: float = 0.5,
    center_within: bool = True,
    below_header_only: bool = False,
    y_gap_tol: float = 2.0
) -> List[int]:
    """
    Return indexes of boxes in nboxes aligned in the same vertical column as header_box.
    """
    hx1, hy1, hx2, hy2 = normalize_box(header_box)
    hw = width(header_box)
    indices = []

    for i, b in enumerate(nboxes):
        bx1, by1, bx2, by2 = normalize_box(b)
        if below_header_only and (by1 + y_gap_tol) < hy2:
            continue

        ov = x_overlap(header_box, b)
        w_min = max(1e-6, min(hw, width(b)))
        ratio = ov / w_min

        if ratio < min_overlap_ratio:
            continue

        if center_within:
            cx = center_x(b)
            if not (hx1 <= cx <= hx2):
                continue

        indices.append(i)

    return indices

def is_header(row):
    if "Trade date" in row or "Valued in USD" in row or "Value of net positions" in row:
        return 1
    return 0
def get_index_by_name(name,texts):
    if name in texts:
        return texts.index(name)
    for idx, col_name in enumerate(texts):
        if name in col_name:
            return idx
    return None

def get_transaction_type(row_json):
    booking_text = " ".join(row_json["Booking text"]).strip()
    booking_text = booking_text.replace("\n", " ").strip()
    if booking_text=="Sec. receipt against payment":
        transaction_type = "Purchase"
    elif booking_text=="Sec. delivery against payment" or booking_text=="Sale Spot":
        transaction_type = "Sale"
    elif "FX Forward" in booking_text:
        transaction_type = "FX Forward"
    elif "Reduction" in booking_text or "Repayment" in booking_text or "Interest Cap." in booking_text:
        transaction_type = "UBS Call Deposit"
    else:
        transaction_type = booking_text.title()
    return transaction_type

def get_isin(row_json):
    description = row_json["Custody account"]
    for e in description:
        if "ISIN" in e:
            parts = e.split("ISIN")
            if len(parts) > 1:
                isin_part = parts[1].strip()
                isin = isin_part.split()[0]
                return isin.split("-")[0]
    return ""

def extract_account_numbers(text: str):
    """
    Extract account numbers of pattern like 546-880515.N1 or 546-880515.09T
    """
    pattern = r"\b\d{3}-\d{6}\.[A-Z0-9]+\b"
    return re.findall(pattern, text)

def convert_date_format(date_str, current_format="%d.%m.%Y", desired_format="%m/%d/%Y"):
    try:
        date_obj = datetime.strptime(date_str, current_format)
        return date_obj.strftime(desired_format)
    except ValueError:
        return None
def is_date(string, date_format="%d.%m.%Y"):
    try:
        datetime.strptime(string, date_format)
        return True
    except ValueError:
        return False

currencies = [
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD",
    "CAD", "CDF", "CHF", "CLP", "CNY", "COP", "CRC", "CUP", "CVE", "CZK",
    "DJF", "DKK", "DOP", "DZD",
    "EGP", "ERN", "ETB", "EUR",
    "FJD", "FKP",
    "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD",
    "HKD", "HNL", "HRK", "HTG", "HUF",
    "IDR", "ILS", "INR", "IQD", "IRR", "ISK",
    "JMD", "JOD", "JPY",
    "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD", "KYD", "KZT",
    "LAK", "LBP", "LKR", "LRD", "LSL", "LYD",
    "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR", "MWK", "MXN", "MYR", "MZN",
    "NAD", "NGN", "NIO", "NOK", "NPR", "NZD",
    "OMR",
    "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
    "QAR",
    "RON", "RSD", "RUB", "RWF",
    "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLL", "SOS", "SRD", "SSP", "STN", "SVC", "SYP", "SZL",
    "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS",
    "UAH", "UGX", "USD", "UYU", "UZS",
    "VES", "VND", "VUV",
    "WST",
    "XAF", "XCD", "XOF", "XPF",
    "YER",
    "ZAR", "ZMW", "ZWL"
]

def get_currency(row_json):
    text = " ".join(row_json["Transaction Tax"] + row_json["Cost/Purchase price"] +row_json["Transaction value"])
    for e in currencies:
        if e in text:
            return e
    return ""

def get_currency_liquidity_account(row_json):
    for e in currencies:
        if e in row_json["By investment category"]:
            return e
    return ""
def get_trade_settlement_date(row_json):
    dates = row_json["Trade date"]
    if "By date" in dates:
        dates.remove("By date")
    if len(dates)==2:
        trade_date, settlement_date = dates
    else:
        trade_date, settlement_date = dates[0], dates[-1]
    trade_date = convert_date_format(trade_date)
    settlement_date = convert_date_format(settlement_date)
    return trade_date, settlement_date

def is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False

def get_quantity(row_json):
    if len(row_json["Transaction Tax"]) == 0:
        return None
    number_amount = row_json["Transaction Tax"][0]
    if is_number(number_amount):
        return float(number_amount)
    else:
        amount= ""
        first_e_split = number_amount.split()
        for idx, e in enumerate(first_e_split):
            if is_number(e):
                amount = amount + e
        if len(amount) >0:
            return float(amount)
    return None

def get_account_no(row_json):
    account_no_list = extract_account_numbers("\n".join(row_json["Custody account"]))
    account_no = row_json["Custody account"][-2].strip()
    return account_no_list[-1]

def get_foreign_unit_price(row_json,transaction_type):
    if transaction_type=="Purchase":
        currency, foreign_unit_price = row_json["Cost/Purchase price"][0].strip().split(" ")[0], "".join(row_json["Cost/Purchase price"][0].strip().split(" ")[1:])
    else:
        currency, foreign_unit_price = row_json["Cost/Purchase price"][0], row_json["Transaction price"][-1]
    foreign_unit_price = re.sub(r"\s+", "", foreign_unit_price).strip()
    # foreign_unit_price= float(foreign_unit_price)
    return foreign_unit_price

def get_foreign_gross_net_consideration(row_json, transaction_type):
    booking_text = " ".join(row_json["Booking text"]).strip()
    booking_text = booking_text.replace("\n", " ").strip()
    if booking_text=="Sale Spot" and len(row_json["Transaction value"])>=3:
        foreign_gross_consideration = row_json["Transaction value"][0]
        foreign_net_consideration = row_json["Transaction value"][-1]
        accrued_interest = row_json["Transaction value"][1]
    else:
        foreign_gross_consideration = row_json["Transaction value"][-1]
        foreign_net_consideration = foreign_gross_consideration
        accrued_interest = ""
    foreign_gross_consideration = re.sub(r"[^0-9.]", "", foreign_gross_consideration).strip()
    foreign_gross_consideration = re.sub(r"\s+", "", foreign_gross_consideration).strip()
    foreign_gross_consideration = abs(float(foreign_gross_consideration))

    foreign_net_consideration = re.sub(r"[^0-9.]", "", foreign_net_consideration).strip()
    foreign_net_consideration = re.sub(r"\s+", "", foreign_net_consideration).strip()
    foreign_net_consideration = abs(float(foreign_net_consideration))


    return foreign_gross_consideration, foreign_net_consideration , accrued_interest


def get_currency_postion(row_json):
    for e in currencies:
        if e in row_json["By investment category"]:
            return e
        for field in row_json:
            for ele in row_json[field]:
                if e in ele:
                    return e
    return ""

def get_isin_position(row_json):
    for e in row_json["Description"]:
        if "ISIN" in e:
            isin = e.split("ISIN")[1].split()[0].strip()
            return isin
    return ""

def get_currency_amount_buy(row_json):
    text = "\n".join(row_json["Custody account"])
    if "bought" in text.strip().split("\n")[0]:
        description_buy =  text.strip().split("\n")[0]
    elif "bought" in text.strip().split("\n")[1]:
        description_buy =  text.strip().split("\n")[1]
    else:
        return "", ""
    description_buy = re.sub("You bought", "", description_buy).strip()
    currency_buy = description_buy.split(" ")[0].strip()
    amount_buy = "".join(description_buy.split(" ")[1:]).strip()
    amount_buy = re.sub(r"\s+", "", amount_buy).strip()
    amount_buy = abs(float(amount_buy))
    return currency_buy, amount_buy

def get_currency_amount_sell(row_json):
    text = "\n".join(row_json["Custody account"])
    if "sold" in text.strip().split("\n")[0]:
        description_sell =  text.strip().split("\n")[0]
    elif "sold" in text.strip().split("\n")[1]:
        description_sell =  text.strip().split("\n")[1]
    else:
        return "", ""
    description_sell = re.sub("You sold", "", description_sell).strip()
    currency_buy = description_sell.split(" ")[0].strip()
    amount_sell = "".join(description_sell.split(" ")[1:]).strip()
    amount_sell = re.sub(r"\s+", "", amount_sell).strip()
    if len(amount_sell)==0:
        amount_sell = ""
    else:
        amount_sell = abs(float(amount_sell))
    return currency_buy, amount_sell

def get_account_no_buy_sell(row_json):
    text = "\n".join(row_json["Custody account"])
    account_buy, account_sell =  text.strip().split("\n")[-2],text.strip().split("\n")[-1]
    account_buy = "-".join(account_buy.split("-")[1:])
    account_sell = "-".join(account_sell.split("-")[1:])
    return account_buy, account_sell

def remove_start_number(text: str) -> str:
    # Remove any combination of numbers and spaces (and optional signs) at the start
    return re.sub(r'^[\s]*[-+]?[\d\s,]+', '', text).strip()

def is_number(s: str) -> bool:
    s = s.strip()
    if s.count('.') > 1:
        return False
    if s.startswith('-'):
        s = s[1:]
    if s=="0":
        return False
    return s.replace('.', '', 1).isdigit()

def get_position_amount(row_json, position_type):
    try:
        for idx, e in enumerate(row_json["By investment category"]):
            row_json["By investment category"][idx] = row_json["By investment category"][idx].replace(" ","")
        if is_number(row_json["By investment category"][-1]):
            amount = row_json["By investment category"][-1]
        elif is_number(row_json["By investment category"][-2]):
            amount = row_json["By investment category"][-2]
        elif is_number(row_json["By investment category"][-3]):
            amount = row_json["By investment category"][-3]
        elif is_number(row_json["By investment category"][-4]):
            amount = row_json["By investment category"][-4]
        else:
            pass
        amount = amount.replace(" ","")
        return float(amount)
    except:
        return ""
def get_position_secuitity_name_amount(row_json, position_type):
    if position_type.strip() in row_json["Description"]:
        row_json["Description"].remove(position_type)
    text = row_json["Description"][0]
    if position_type in ["Bonds - Bond investments", "Equities - Equity investments", "Money market investments","Equities - Structured products & derivatives","Liquidity - FX swap & forward contracts"]:
        if position_type in text:
            text = text.split(position_type)[1].strip()
        first_e = text.split("\n")[0].strip()
        first_e_check = re.sub(r"\s+", "", text.split("\n")[0]).strip()
        if is_number(first_e_check):
            return text.strip().split("\n")[1],text.strip().split("\n")[0]
        else:
            first_e_split = first_e.split()
            amount = []
            name_s_idx = 0
            for idx, e in enumerate(first_e_split):
                if is_number(e):
                    amount.append(e)
                else:
                    name_s_idx =idx
                    break
            if len(amount)>0:
                amount_number = "".join(amount)
                return " ".join(first_e_split[name_s_idx:]),amount_number
            else:
                return " ".join(first_e_split[name_s_idx:]),""
    else:
        return "", ""
    
def get_position_cost_price(row_json, position_type):
    try:
        texts = row_json["Cost price"]
        cost_price = texts[0]
        cost_price = re.sub(r'[^0-9.%]+', '', cost_price)
        if "%" in cost_price:
            return float(cost_price.strip('%')) / 100
        cost_price = float(cost_price)
        return cost_price
    except:
        return ""

def get_market_price(row_json, position_type):
    try:
        text = row_json["Market price"][0]
        market_price = re.sub(r"[^0-9%.]", "", text).strip()
        if "%" in market_price:
            return float(market_price.strip('%')) / 100
        else:
            return float(market_price)
    except:
        return ""

def get_market_value(row_json, position_type):
    try:
        text = row_json["Market value"][0]
        market_value = re.sub(r"[^0-9.]", "", text).strip()
        if "%" in market_value:
            return float(market_value.strip('%')) / 100
        else:
            return float(market_value)
    except:
        return ""


def get_row_type(row_json):
    for field in row_json:
        for ele in row_json[field]:
            if "Subtotal" in ele or ("Total" in ele):
                return "subtotal"
    if len(row_json['Description'])==0:
        return "empty" 
    return "normal"

def get_liquidity_row_type(row_json):
    for field in row_json:
        for ele in row_json[field]:
            if "Total" in ele:
                return "subtotal"
    return "normal"


def get_position_type(row):
    row["text"] = " ".join(row["text"])
    if "Bonds - Bond" in row["text"]:
        return "Bonds - Bond investments"
    elif "Equities - Equity investments" in row["text"]:
        return "Equities - Equity investments"
    elif "Equities - Structured products & derivatives" in row["text"]:
        return "Equities - Structured products & derivatives"
    elif "Liquidity - Accounts" in row['text']:
        return "Liquidity - Accounts"
    elif "Liquidity - Call deposits" in row["text"]:
        return "Liquidity - Call deposits"
    elif "market investments" in row["text"]:
        return "Liquidity - Money market investments"
    elif "Liquidity - Money market investments" in row["text"]:
        return "Liquidity - Money market investments"
    elif "Liquidity - FX swap & forward contracts" in row["text"]:
        return "Liquidity - FX swap & forward contracts"
    else:
        return ""
    
def get_liquidity_amount(row_json):
    amount = ""
    if len(row_json["By investment category"])==1:
        try:
            amount = row_json["Description"][0].lower().split("ubs")[0].strip()
            amount = amount.replace(" ","")
            amount = float(amount)
        except:
            amount = ""
    elif len(row_json["By investment category"])==2:
        amount_str = row_json["By investment category"][-1]
        try:
            amount = float(amount_str.replace(" ",""))
        except:
            try:
                amount = row_json["Description"][0].lower().split("ubs")[0].strip()
                amount = amount.replace(" ","")
                amount = float(amount)
            except:
                amount = ''
    return amount

def get_secuitity_name(row_json,position_type):
    if row_json["Description"][0]=="ts" or row_json["Description"][0]==position_type:
        secuitity_name = row_json["Description"][1] + " " +  row_json["Description"][2] if not any(char.isdigit() for char in row_json["Description"][2]) else row_json["Description"][1]
    else:
        secuitity_name = row_json["Description"][0] + " " +  row_json["Description"][1] if not any(char.isdigit() for char in row_json["Description"][1]) else row_json["Description"][0]

    return secuitity_name