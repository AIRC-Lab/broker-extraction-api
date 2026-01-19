from typing import List, Tuple, Union
from datetime import datetime
import re
from decimal import Decimal, InvalidOperation

Box = Tuple[float, float, float, float]  # (x1, y1, x2, y2)


def normalize_box(box: Box) -> Box:
    """Ensure (x1, y1) is top-left and (x2, y2) is bottom-right."""
    x1, y1, x2, y2 = box
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def box_contains(outer: Box, inner: Box, threshold: float = 0.8) -> bool:
    """
    Determine if the overlap (IoU-like) between the outer and inner boxes
    is greater than a specified threshold.
    (NOTE: This divides by inner area (areaB).)
    """

    def iou_like(boxA: Box, boxB: Box) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        inter_width = max(0, xB - xA)
        inter_height = max(0, yB - yA)
        intersection = inter_width * inter_height

        areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        union = areaB

        if union == 0:
            return 0.0
        return intersection / union

    return iou_like(outer, inner) > threshold


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

    Returns:
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
    # row may be list of tokens or a string
    if isinstance(row, (list, tuple)):
        text = " ".join(row)
    else:
        text = str(row)

    low = text.lower()

    # quick legacy checks
    if "trade date" in low or "valued in usd" in low or "value of net positions" in low:
        return True

    header_keywords = [
        "description", "number/amount", "cost price", "market price", "market value",
        "market gain", "transaction value", "booking text", "trade date", "by investment category",
        "% na", "s&p", "moodys", "duration", "yield", "settlement", "valued in"
    ]

    hits = sum(1 for k in header_keywords if k in low)

    # explicit column names
    explicit_hits = 0
    for col in transaction_columns + position_columns + liquidity_account_columns:
        if col and col.lower() in low:
            explicit_hits += 1

    if hits + explicit_hits >= 2:
        return True

    # uppercase short tokens likely header
    tokens = text.strip().split()
    if 1 <= len(tokens) <= 4 and text.strip().isupper():
        return True

    return False


# ==========================================================
# ✅ FIX: tolerant header matching (case-insensitive, ignore punctuation)
# Only change needed to "restore missing position info" without breaking others.
# ==========================================================

def _norm_header_text(s: str) -> str:
    """
    Normalize OCR header text:
    - lower case
    - remove punctuation/symbols
    - keep alnum + space
    - collapse spaces
    """
    if s is None:
        return ""
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)   # remove .,;:/()- etc
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _header_aliases(name: str) -> List[str]:
    """
    Small alias list for common OCR variations (mainly position headers).
    Keep it minimal to avoid affecting other files.
    """
    n = _norm_header_text(name)

    aliases = [n]
    # Common truncations / OCR mistakes (position)
    if n == "market value":
        aliases += ["market valu", "market val", "mkt value", "mkt val"]
    if n == "market price":
        aliases += ["market pric", "mkt price", "mkt pric"]
    if n == "cost price":
        aliases += ["cost pric", "purchase price", "purchase pric"]
    if n == "by investment category":
        aliases += ["investment category", "by investment", "investment cat", "inv category"]
    if n == "description":
        aliases += ["descr", "descript", "security name", "security", "security name description"]
    if n == "duration":
        aliases += ["duratio", "durat", "maturity", "tenor"]

    # Transaction headers (keep light)
    if n == "booking text":
        aliases += ["booking", "booking tex", "booking txt"]
    if n == "custody account":
        aliases += ["custody", "account", "custody acc", "custody acct"]

    # remove duplicates
    out = []
    seen = set()
    for a in aliases:
        a = _norm_header_text(a)
        if not a or a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


def get_index_by_name(name, texts):
    """
    Find header index in OCR texts robustly:
    1) exact match (old behavior)
    2) substring match (old behavior)
    3) tolerant match: ignore punctuation + case-insensitive + alias + token overlap
    """
    if not texts:
        return None

    # 1) exact match (keep old behavior)
    if name in texts:
        return texts.index(name)

    # 2) substring match (keep old behavior)
    for idx, col_name in enumerate(texts):
        try:
            if col_name and name in col_name:
                return idx
        except Exception:
            continue

    # 3) tolerant match
    name_aliases = _header_aliases(name)
    if not name_aliases:
        return None

    # Build normalized list once
    norm_texts = []
    for t in texts:
        norm_texts.append(_norm_header_text(t))

    best_idx = None
    best_score = -1

    for idx, tnorm in enumerate(norm_texts):
        if not tnorm:
            continue

        # Prefer exact normalized / substring for any alias
        for alias in name_aliases:
            if not alias:
                continue
            if alias == tnorm:
                return idx
            if alias in tnorm or tnorm in alias:
                # substring match score by length overlap
                score = min(len(alias), len(tnorm))
                if score > best_score:
                    best_score = score
                    best_idx = idx

        # Token overlap fallback:
        # require at least 2 tokens overlap when possible, else 1 for single-word headers
        t_tokens = set(tnorm.split())
        for alias in name_aliases:
            a_tokens = set(alias.split())
            if not a_tokens or not t_tokens:
                continue
            inter = len(a_tokens & t_tokens)
            if len(a_tokens) >= 2:
                if inter >= 2 and inter > best_score:
                    best_score = inter
                    best_idx = idx
            else:
                if inter >= 1 and inter > best_score:
                    best_score = inter
                    best_idx = idx

    return best_idx


def get_transaction_type(row_json):
    booking_text = " ".join(row_json.get("Booking text", [])).strip()
    booking_text = booking_text.replace("\n", " ").strip()

    if booking_text == "Sec. receipt against payment":
        return "Purchase"
    elif booking_text == "Sec. delivery against payment" or booking_text == "Sale Spot":
        return "Sale"
    elif "FX Forward" in booking_text:
        return "FX Forward"
    elif "Reduction" in booking_text or "Repayment" in booking_text or "Interest Cap." in booking_text:
        return "UBS Call Deposit"
    else:
        return booking_text.title()


def get_isin(row_json):
    description = row_json.get("Custody account", [])
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


def get_valuation_date_from_text(text: str):
    """
    Extract valuation date from header text. Handles patterns like:
      - 'Statement of assets as of 31 March 2025'
      - 'Valuation date: 31.03.2025' (dd.mm.yyyy)
      - 'Valued as at 31.03.25'
    Returns MM/DD/YYYY or empty string.
    """
    if not text:
        return ""

    # 1) 'Statement of assets as of 31 March 2025'
    m = re.search(r"statement of assets.*?as of\s+([0-3]?\d)\s+([A-Za-z]+)\s+(\d{4})", text, flags=re.IGNORECASE)
    if m:
        day, mon_name, year = m.group(1), m.group(2), m.group(3)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(f"{day} {mon_name} {year}", fmt)
                return dt.strftime("%m/%d/%Y")
            except Exception:
                continue

    # 2) 'Valuation date: 31.03.2025' or similar
    m = re.search(r"valuation date[:\s]*([0-3]?\d\.[01]?\d\.(?:\d{2}|\d{4}))", text, flags=re.IGNORECASE)
    if m:
        d = m.group(1)
        parts = d.split('.')
        if len(parts[-1]) == 2:
            parts[-1] = '20' + parts[-1]
            d = '.'.join(parts)
        out = convert_date_format(d)
        if out:
            return out

    # 3) any dd.mm.yy or dd.mm.yyyy elsewhere
    m = re.search(r"([0-3]?\d\.[01]?\d\.(?:\d{2}|\d{4}))", text)
    if m:
        d = m.group(1)
        parts = d.split('.')
        if len(parts[-1]) == 2:
            parts[-1] = '20' + parts[-1]
            d = '.'.join(parts)
        out = convert_date_format(d)
        if out:
            return out

    # 4) fallback: english date like '31 March 2025'
    m2 = re.search(r"([0-3]?\d)\s+([A-Za-z]+)\s+(\d{4})", text)
    if m2:
        day, mon_name, year = m2.group(1), m2.group(2), m2.group(3)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(f"{day} {mon_name} {year}", fmt)
                return dt.strftime("%m/%d/%Y")
            except Exception:
                continue

    return ""


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
    text = " ".join(
        row_json.get("Transaction Tax", [])
        + row_json.get("Cost/Purchase price", [])
        + row_json.get("Transaction value", [])
    )
    for e in currencies:
        if e in text:
            return e
    return ""


def get_currency_liquidity_account(row_json):
    for e in currencies:
        if e in row_json.get("By investment category", []):
            return e
    return ""


def get_trade_settlement_date(row_json):
    dates = row_json.get("Trade date", [])
    if "By date" in dates:
        dates.remove("By date")
    if len(dates) == 2:
        trade_date, settlement_date = dates
    elif len(dates) > 0:
        trade_date, settlement_date = dates[0], dates[-1]
    else:
        return None, None

    trade_date = convert_date_format(trade_date)
    settlement_date = convert_date_format(settlement_date)
    return trade_date, settlement_date


def is_number(s: str) -> bool:
    try:
        v = _parse_signed_number_string(s)
        return v != ""
    except Exception:
        return False


def get_quantity(row_json):
    if len(row_json.get("Transaction Tax", [])) == 0:
        return None
    number_amount = row_json["Transaction Tax"][0]
    if is_number(number_amount):
        v = _parse_signed_number_string(number_amount)
        return v
    else:
        amount = ""
        first_e_split = number_amount.split()
        for e in first_e_split:
            if is_number(e):
                amount = amount + e
        if len(amount) > 0:
            return _parse_signed_number_string(amount)
    return None


def get_account_no(row_json):
    account_no_list = extract_account_numbers("\n".join(row_json.get("Custody account", [])))
    return account_no_list[-1] if account_no_list else ""


def extract_portfolio_numbers(text: str):
    """
    Extract portfolio numbers like 546-880515-01
    """
    pattern = r"\b\d{3}-\d{6}-\d{2}\b"
    return re.findall(pattern, text)


def get_portfolio_no_from_text(text: str):
    nums = extract_portfolio_numbers(text)
    return nums[0] if nums else ""


# ==========================================================
# ✅ CLIENT NAME (FIXED): basic rule exactly as you said
#   Between "Portfolio number <...>" and "Statement of assets ..."
#   Works even when OCR is token list (rec_texts) with no newlines.
# ==========================================================
def get_client_name_from_text(text: Union[str, List[str]]):
    """
    BASIC RULE (yours):
      - Find "Portfolio number"
      - Find portfolio number token like 546-880515-01 after it
      - Client name = all tokens AFTER portfolio number and BEFORE "Statement of assets"
      - No heuristic scoring, no guessing.
    """

    # 1) Normalize input to tokens list (best for Paddle rec_texts)
    if text is None:
        return ""

    if isinstance(text, list):
        tokens = []
        for t in text:
            if t is None:
                continue
            s = str(t).strip()
            if not s:
                continue
            s = re.sub(r"\s+", " ", s).strip()
            tokens.append(s)
        flat = " ".join(tokens)
    else:
        s = str(text)
        s = s.replace("\n", " ")
        s = re.sub(r"\s+", " ", s).strip()
        flat = s
        tokens = [x for x in flat.split(" ") if x]

    if not tokens:
        return ""

    def low(t: str) -> str:
        return (t or "").lower().strip()

    # 2) Find "portfolio number" index in tokens (tolerant)
    port_idx = None
    for i in range(len(tokens)):
        if low(tokens[i]) == "portfolio" and i + 1 < len(tokens) and low(tokens[i + 1]) in ("number", "no", "no."):
            port_idx = i
            break
        if "portfolio" in low(tokens[i]) and ("number" in low(tokens[i]) or "no" == low(tokens[i])):
            port_idx = i
            break

    if port_idx is None:
        m = re.search(
            r"portfolio\s+(?:number|no\.?)\s+(\d{3}-\d{6}-\d{2})\s+(.*?)\s+statement\s+of\s+assets",
            flat, flags=re.IGNORECASE
        )
        if m:
            name = (m.group(2) or "").strip()
            name = re.sub(r"\s+", " ", name).strip()
            return name
        return ""

    # 3) Find portfolio number token after "portfolio number"
    portfolio_no = None
    portfolio_pos = None
    for j in range(port_idx, min(port_idx + 20, len(tokens))):
        m = re.search(r"\b\d{3}-\d{6}-\d{2}\b", tokens[j])
        if m:
            portfolio_no = m.group(0)
            portfolio_pos = j
            break

    if portfolio_no is None or portfolio_pos is None:
        m = re.search(
            r"portfolio\s+(?:number|no\.?)\s+(\d{3}-\d{6}-\d{2})\s+(.*?)\s+statement\s+of\s+assets",
            flat, flags=re.IGNORECASE
        )
        if m:
            name = (m.group(2) or "").strip()
            name = re.sub(r"\s+", " ", name).strip()
            return name
        return ""

    # 4) Find "statement of assets" index after portfolio number
    stmt_idx = None
    for k in range(portfolio_pos + 1, len(tokens)):
        if low(tokens[k]) == "statement":
            if k + 2 < len(tokens) and low(tokens[k + 1]) == "of" and low(tokens[k + 2]) == "assets":
                stmt_idx = k
                break
        if "statement" in low(tokens[k]) and "assets" in low(tokens[k]):
            stmt_idx = k
            break

    if stmt_idx is None:
        m = re.search(
            r"portfolio\s+(?:number|no\.?)\s+\d{3}-\d{6}-\d{2}\s+(.*?)\s+statement\s+of\s+assets",
            flat, flags=re.IGNORECASE
        )
        if m:
            name = (m.group(1) or "").strip()
            name = re.sub(r"\s+", " ", name).strip()
            return name
        return ""

    # 5) Client name tokens are between portfolio_pos and stmt_idx
    name_tokens = tokens[portfolio_pos + 1:stmt_idx]
    name = " ".join(name_tokens).strip()
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(" -|:;")
    return name


def get_foreign_unit_price(row_json, transaction_type):
    if transaction_type == "Purchase":
        parts = row_json.get("Cost/Purchase price", [""])
        if parts and parts[0]:
            foreign_unit_price = "".join(parts[0].strip().split(" ")[1:])
        else:
            foreign_unit_price = ""
    else:
        tp = row_json.get("Transaction price", [])
        foreign_unit_price = tp[-1] if tp else ""
    foreign_unit_price = re.sub(r"\s+", "", foreign_unit_price).strip()
    return foreign_unit_price


def get_foreign_gross_net_consideration(row_json, transaction_type):
    booking_text = " ".join(row_json.get("Booking text", [])).strip()
    booking_text = booking_text.replace("\n", " ").strip()

    txv = row_json.get("Transaction value", [])

    if booking_text == "Sale Spot" and len(txv) >= 3:
        foreign_gross_consideration = txv[0]
        foreign_net_consideration = txv[-1]
        accrued_interest = txv[1]
    else:
        foreign_gross_consideration = txv[-1] if txv else ""
        foreign_net_consideration = foreign_gross_consideration
        accrued_interest = ""

    fg = _parse_signed_number_string(foreign_gross_consideration)
    fn = _parse_signed_number_string(foreign_net_consideration)

    if fg == "":
        fg = Decimal('0')
    if fn == "":
        fn = Decimal('0')

    try:
        fg = abs(Decimal(fg))
    except Exception:
        fg = Decimal('0')
    try:
        fn = abs(Decimal(fn))
    except Exception:
        fn = Decimal('0')

    return fg, fn, accrued_interest


# =========================
# ✅ FX Forward helpers (ONLY for fx_tf)
# =========================
def _parse_signed_number_string(num_str: str):
    """
    Parse a numeric string that may contain spaces/commas and optional sign.
    Keep the sign if present.
    """
    if not num_str:
        return ""
    s = str(num_str).strip()

    s = s.replace("−", "-").replace("–", "-")

    neg_by_paren = False
    if "(" in s and ")" in s:
        neg_by_paren = True

    s_clean = re.sub(r"[^0-9\-\+\s,\.()]", "", s).strip()
    if not s_clean:
        return ""

    s_no_paren = s_clean.replace("(", "").replace(")", "")

    dot_pos = s_no_paren.rfind('.')
    comma_pos = s_no_paren.rfind(',')
    decimal_sep = None
    if dot_pos != -1 and comma_pos != -1:
        if comma_pos > dot_pos:
            decimal_sep = ','
        else:
            decimal_sep = '.'
    elif comma_pos != -1 and dot_pos == -1:
        m = re.search(r",\d{3}(?:[^\d]|$)", s_no_paren)
        if m:
            decimal_sep = None
        else:
            decimal_sep = ','
    else:
        decimal_sep = '.'

    normalized = s_no_paren
    normalized = normalized.replace(' ', '')
    if decimal_sep == ',':
        normalized = normalized.replace('.', '')
        normalized = normalized.replace(',', '.')
    else:
        normalized = normalized.replace(',', '')

    normalized = re.sub(r"[^0-9\-\+\.]", "", normalized)

    try:
        val = Decimal(normalized)
        if neg_by_paren and val > 0:
            val = -val
        return val
    except (InvalidOperation, ValueError):
        return ""


# ==========================================================
# ✅ QUANTITY FIX (ONLY): split leading quantity from coupon% at start of name
# ==========================================================
def _split_qty_and_coupon_prefix(text: str):
    if not text or not isinstance(text, str):
        return None, text

    s = re.sub(r"\s+", " ", text).strip()
    if not s or not s[0].isdigit():
        return None, s

    compact = s.replace(" ", "")

    m_pct = re.search(r"(\d+(?:[.,]\d+)?)%", compact)
    if not m_pct:
        return None, s

    pct_start = m_pct.start(1)
    pct_end = m_pct.end(0)

    qty_candidate_compact = compact[:pct_start]
    coupon_compact = compact[pct_start:pct_end]
    rest_compact = compact[pct_end:]

    if not qty_candidate_compact or len(re.sub(r"[^\d]", "", qty_candidate_compact)) < 3:
        return None, s

    qty_digits = re.sub(r"[^\d]", "", qty_candidate_compact)
    if not qty_digits:
        return None, s

    try:
        qty_val = Decimal(qty_digits)
    except Exception:
        return None, s

    coupon_norm = coupon_compact.replace(",", ".")
    name_rest = (coupon_norm + rest_compact).strip()
    return qty_val, name_rest


def _compact_lower(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", "", s.lower()).strip()


def _extract_ccy_amount_pairs(lines: List[str]):
    pairs = []
    if not lines:
        return pairs

    for ln in lines:
        if not ln:
            continue
        t = re.sub(r"\s+", " ", str(ln)).strip()
        if not t:
            continue

        for m in re.finditer(r"\b([A-Z]{3})\s+([+\-]?\d[\d\s,\.()\-]*)", t):
            ccy = (m.group(1) or "").strip()
            amt_raw = (m.group(2) or "").strip()
            amt = _parse_signed_number_string(amt_raw)
            if ccy and isinstance(amt, (int, float, Decimal)):
                pairs.append((ccy, amt))

    seen = set()
    out = []
    for ccy, amt in pairs:
        key = (ccy, amt)
        if key in seen:
            continue
        seen.add(key)
        out.append((ccy, amt))
    return out


def _extract_fx_amount_line(lines: List[str], verb: str):
    if not lines:
        return "", ""

    verb_key = f"you{verb}"
    verb_regex = "".join([ch + r"\s*" for ch in verb])

    for ln in lines:
        if not ln:
            continue
        t = re.sub(r"\s+", " ", str(ln)).strip()
        if not t:
            continue

        low_compact = _compact_lower(t)
        if verb_key not in low_compact:
            continue

        m = re.search(
            rf"\byou\s*{verb_regex}\s*([A-Z]{{3}})\s*([+\-]?\d[\d\s,\.()\-]*)",
            t,
            flags=re.IGNORECASE
        )
        if not m:
            mm = re.search(r"\b([A-Z]{3})\s+([+\-]?\d[\d\s,\.()\-]*)", t)
            if not mm:
                continue
            cur = (mm.group(1) or "").strip()
            amt = _parse_signed_number_string((mm.group(2) or "").strip())
        else:
            cur = (m.group(1) or "").strip()
            amt = _parse_signed_number_string((m.group(2) or "").strip())

        if verb == "sold" and isinstance(amt, (int, float, Decimal)):
            if amt > 0:
                amt = -amt

        return cur, amt

    pairs = _extract_ccy_amount_pairs(lines)
    if len(pairs) >= 2:
        buy_ccy, buy_amt = pairs[0]
        sell_ccy, sell_amt = pairs[1]

        if verb == "bought":
            return buy_ccy, buy_amt
        else:
            if isinstance(sell_amt, (int, float, Decimal)) and sell_amt > 0:
                sell_amt = -sell_amt
            return sell_ccy, sell_amt

    return "", ""


def get_currency_amount_buy(row_json):
    lines = row_json.get("Custody account", [])
    return _extract_fx_amount_line(lines, verb="bought")


def get_currency_amount_sell(row_json):
    lines = row_json.get("Custody account", [])
    return _extract_fx_amount_line(lines, verb="sold")


def get_fx_forward_rate(row_json):
    candidates = []
    candidates.extend(row_json.get("Cost/Purchase price", []))
    candidates.extend(row_json.get("Transaction price", []))
    candidates.extend(row_json.get("Transaction value", []))
    candidates.extend(row_json.get("Booking text", []))

    for c in candidates:
        if not c:
            continue
        t = re.sub(r"\s+", " ", str(c)).strip()
        if not t:
            continue

        m = re.search(r"([0-9]+(?:[\.,][0-9]+)?)", t)
        if not m:
            continue

        rate_str = m.group(1).replace(',', '.')
        try:
            return Decimal(rate_str)
        except Exception:
            continue

    return ""


def get_account_no_buy_sell(row_json):
    text = "\n".join(row_json.get("Custody account", []))
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return "", ""
    account_buy, account_sell = lines[-2], lines[-1]
    account_buy = "-".join(account_buy.split("-")[1:])
    account_sell = "-".join(account_sell.split("-")[1:])

    account_buy = account_buy.replace(",", ".")
    account_sell = account_sell.replace(",", ".")

    return account_buy, account_sell


def remove_start_number(text: str) -> str:
    return re.sub(r'^[\s]*[-+]?[\d\s,]+', '', text).strip()


def is_account_no_like(s: str) -> bool:
    if not s:
        return False
    return bool(re.search(r"\b\d{3}-\d{6}\.[A-Z0-9]+\b", s))


def split_leading_quantity_general(text: str):
    if not text or not isinstance(text, str):
        return None, text

    s = text.strip()
    if not s or not s[0].isdigit():
        return None, s

    qty_coupon, rest_after_coupon = _split_qty_and_coupon_prefix(s)
    if qty_coupon is not None:
        return qty_coupon, rest_after_coupon

    m = re.match(r"^([0-9][0-9\s,\.]*)\s+(.*)$", s)
    if not m:
        return None, s

    qty_raw = (m.group(1) or "").strip()
    rest = (m.group(2) or "").strip()

    if rest.startswith("%"):
        return None, s

    has_thousand_sep = (" " in qty_raw) or ("," in qty_raw)
    has_decimal = "." in qty_raw
    qty_digits_only = re.sub(r"[^\d]", "", qty_raw)
    long_integer = (len(qty_digits_only) >= 5) and (not has_decimal)

    if not (has_thousand_sep or long_integer):
        return None, s

    qty_norm = qty_raw.replace(" ", "").replace(",", "")
    try:
        qty = Decimal(qty_norm)
    except Exception:
        return None, s

    return qty, rest


def split_leading_quantity_position(text: str):
    if not text or not isinstance(text, str):
        return None, text

    s = re.sub(r"\s+", " ", text).strip()
    if not s:
        return None, s

    if re.match(r"^\d+(\.\d+)?\s*%", s):
        return None, s

    if not s[0].isdigit():
        return None, s

    qty_coupon, rest_after_coupon = _split_qty_and_coupon_prefix(s)
    if qty_coupon is not None:
        return qty_coupon, rest_after_coupon

    m = re.match(r"^([0-9][0-9\s,\.oO]*)\s+(.*)$", s)
    if not m:
        return None, s

    qty_raw = (m.group(1) or "").strip()
    rest = (m.group(2) or "").strip()

    qty_raw_norm = qty_raw.replace("O", "0").replace("o", "0")
    qty_digits = re.sub(r"[^\d]", "", qty_raw_norm)

    has_sep = (" " in qty_raw_norm) or ("," in qty_raw_norm)
    if not (has_sep or len(qty_digits) >= 3):
        return None, s

    if not qty_digits:
        return None, s

    try:
        qty = Decimal(qty_digits)
    except Exception:
        return None, s

    rest = re.sub(r"\s+", " ", rest).strip()
    return qty, rest


def _looks_like_noise_line_for_security_name(line: str) -> bool:
    if not line:
        return True

    s = re.sub(r"\s+", " ", line).strip()
    low = s.lower()

    if low.startswith("you bought") or low.startswith("you sold"):
        return True

    if "isin" in low:
        return True

    if is_account_no_like(s):
        return True

    noise_keywords = [
        "settlement", "settle", "reference", "ref.", "ref:",
        "place of execution", "execution", "broker", "counterparty",
        "custody", "account", "our ref", "your ref",
        "fees", "commission", "tax", "withholding",
        "swift", "instruction", "depository", "clearstream", "euroclear",
        "value date", "valuedate", "payment", "against payment", "free of payment",
        "trade no", "trade number", "deal no", "deal number",
        "order", "order no", "order number",
        "settlement no", "settlement number", "settlement n", "settlement#", "settlement #",
        "contract", "contract no", "contract number",
        "confirmation", "confirm",
        "location", "market", "venue",
    ]
    for kw in noise_keywords:
        if kw in low:
            return True

    if re.fullmatch(r"[A-Z0-9\-/]{6,}", s) and (" " not in s):
        return True

    return False


def _is_strong_stop_line(line: str) -> bool:
    if not line:
        return False
    s = re.sub(r"\s+", " ", line).strip()
    low = s.lower()

    if is_account_no_like(s):
        return True

    stop_keywords = [
        "settlement", "place of execution", "broker", "counterparty",
        "reference", "ref.", "ref:", "our ref", "your ref",
        "trade no", "deal no", "order no", "contract",
        "confirmation", "swift", "instruction",
    ]
    for kw in stop_keywords:
        if kw in low:
            return True

    return False


def build_security_name_from_custody_account_lines(lines: List[str]) -> str:
    if not lines:
        return ""

    cleaned_name_lines: List[str] = []
    for ln in lines:
        if not ln:
            continue
        t = re.sub(r"\s+", " ", ln).strip()
        if not t:
            continue

        if _is_strong_stop_line(t):
            break

        if _looks_like_noise_line_for_security_name(t):
            continue

        cleaned_name_lines.append(t)

        if len(cleaned_name_lines) >= 2:
            break

    name = " ".join(cleaned_name_lines).strip()
    name = re.sub(r"\s+", " ", name).strip()
    try:
        qty, rest = split_leading_quantity_general(name)
        if qty is not None and rest:
            name = rest
    except Exception:
        pass

    name = re.sub(r"\bISIN\b[:\s]*[A-Z0-9\-]+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", name)
    name = re.sub(r"\b(as of|as at|dated)\b.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*\([^)]*\)\s*", " ", name)
    name = re.sub(r"[\)\(\"\']+", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


def _is_negative_hint_text(s: str) -> bool:
    if not s:
        return False
    t = str(s)
    if "-" in t or "−" in t or "–" in t:
        return True
    if "(" in t and ")" in t:
        return True
    return False


def get_foreign_gross_net_consideration_other(row_json):
    booking_text = " ".join(row_json.get("Booking text", [])).strip()
    booking_text = booking_text.replace("\n", " ").strip()
    bt_low = booking_text.lower()

    txv = row_json.get("Transaction value", [])

    if booking_text == "Sale Spot" and len(txv) >= 3:
        gross_raw = txv[0]
        net_raw = txv[-1]
        accrued_interest = txv[1]
    else:
        gross_raw = txv[-1] if txv else ""
        net_raw = gross_raw
        accrued_interest = ""

    gross_val = _parse_signed_number_string(gross_raw)
    net_val = _parse_signed_number_string(net_raw)

    should_be_negative = ("reduction" in bt_low) or ("repayment" in bt_low)
    should_be_positive = ("interest cap" in bt_low) or ("interest" in bt_low)

    if isinstance(gross_val, (int, float, Decimal)) and gross_val > 0:
        if should_be_negative and (not _is_negative_hint_text(gross_raw)):
            gross_val = -gross_val
    if isinstance(net_val, (int, float, Decimal)) and net_val > 0:
        if should_be_negative and (not _is_negative_hint_text(net_raw)):
            net_val = -net_val

    if isinstance(gross_val, (int, float, Decimal)) and gross_val < 0 and should_be_positive and (not should_be_negative):
        gross_val = abs(gross_val)
    if isinstance(net_val, (int, float, Decimal)) and net_val < 0 and should_be_positive and (not should_be_negative):
        net_val = abs(net_val)

    if gross_val == "":
        gross_val = Decimal('0')
    if net_val == "":
        net_val = Decimal('0')

    return gross_val, net_val, accrued_interest


def get_currency_position(row_json):
    for e in currencies:
        if e in row_json.get("By investment category", []):
            return e
        for field in row_json:
            for ele in row_json[field]:
                if e in ele:
                    return e
    return ""


def get_currency_postion(row_json):
    return get_currency_position(row_json)


def get_isin_position(row_json):
    for e in row_json.get("Description", []):
        if "ISIN" in e:
            isin = e.split("ISIN")[1].split()[0].strip()
            return isin
    return ""


def is_number_strict(s: str) -> bool:
    s = s.strip()
    if s.count('.') > 1:
        return False
    if s.startswith('-'):
        s = s[1:]
    if s == "0":
        return False
    return s.replace('.', '', 1).isdigit()


def get_position_amount(row_json, position_type):
    """
    NOTE: kept structure the same; only made it more tolerant to separators
    so Quantity/Amount does not get missed when OCR uses spaces/commas/dots.
    """
    try:
        for idx, e in enumerate(row_json["By investment category"]):
            row_json["By investment category"][idx] = row_json["By investment category"][idx].replace(" ", "")

        amount = ""
        if len(row_json["By investment category"]) >= 1 and is_number_strict(row_json["By investment category"][-1]):
            amount = row_json["By investment category"][-1]
        elif len(row_json["By investment category"]) >= 2 and is_number_strict(row_json["By investment category"][-2]):
            amount = row_json["By investment category"][-2]
        elif len(row_json["By investment category"]) >= 3 and is_number_strict(row_json["By investment category"][-3]):
            amount = row_json["By investment category"][-3]
        elif len(row_json["By investment category"]) >= 4 and is_number_strict(row_json["By investment category"][-4]):
            amount = row_json["By investment category"][-4]

        amount = amount.replace(" ", "")
        parsed = _parse_signed_number_string(amount)
        if parsed != "":
            return parsed
        try:
            return Decimal(amount) if amount else ""
        except Exception:
            return ""
    except:
        return ""


def get_position_cost_price(row_json, position_type):
    try:
        texts = row_json.get("Cost price", [])
        cost_price = texts[0]
        m = re.search(r"([+\-]?[0-9\s\.,()]+%?)", cost_price)
        if not m:
            return ""
        token = m.group(1)
        if '%' in token:
            token_clean = token.replace('%', '').strip()
            val = _parse_signed_number_string(token_clean)
            try:
                return Decimal(val) / Decimal('100')
            except Exception:
                return ""
        else:
            val = _parse_signed_number_string(token)
            return val if val != "" else ""
    except:
        return ""


def get_market_price(row_json, position_type):
    try:
        text = row_json.get("Market price", [])[0]
        m = re.search(r"([+\-]?[0-9\s\.,()]+%?)", text)
        if not m:
            return ""
        token = m.group(1)
        if '%' in token:
            v = _parse_signed_number_string(token.replace('%', ''))
            try:
                return Decimal(v) / Decimal('100')
            except Exception:
                return ""
        else:
            v = _parse_signed_number_string(token)
            return v if v != "" else ""
    except:
        return ""


def get_market_value(row_json, position_type):
    try:
        text = row_json.get("Market value", [])[0]
        m = re.search(r"([+\-]?[0-9\s\.,()]+%?)", text)
        if not m:
            return ""
        token = m.group(1)
        if '%' in token:
            v = _parse_signed_number_string(token.replace('%', ''))
            try:
                return Decimal(v) / Decimal('100')
            except Exception:
                return ""
        else:
            v = _parse_signed_number_string(token)
            return v if v != "" else ""
    except:
        return ""


def get_row_type(row_json):
    for field in row_json:
        for ele in row_json[field]:
            if "Subtotal" in ele or ("Total" in ele):
                return "subtotal"
    if len(row_json.get('Description', [])) == 0:
        return "empty"
    return "normal"


def get_liquidity_row_type(row_json):
    for field in row_json:
        for ele in row_json[field]:
            if "Total" in ele:
                return "subtotal"
    return "normal"


# ==========================================================
# ✅ POSITION TYPE (FIXED)
# - Adds Hedge funds
# - More tolerant FX swap/forward detection
# - DOES NOT mutate row["text"]
# ==========================================================
def get_position_type(row):
    tokens = row.get("text", [])
    if isinstance(tokens, (list, tuple)):
        text = " ".join([str(x) for x in tokens if x is not None])
    else:
        text = str(tokens)

    text = re.sub(r"\s+", " ", text).strip()
    low = text.lower()

    # ✅ Hedge funds
    if re.fullmatch(r"\s*hedge\s+funds\s*", low):
        return "Hedge funds"

    if "Bonds - Bond" in text:
        return "Bonds - Bond investments"
    elif "Equities - Equity investments" in text:
        return "Equities - Equity investments"
    elif "Equities - Structured products & derivatives" in text:
        return "Equities - Structured products & derivatives"
    elif "Liquidity - Accounts" in text:
        return "Liquidity - Accounts"
    elif "Liquidity - Call deposits" in text:
        return "Liquidity - Call deposits"

    # Money market investments (tolerant)
    elif ("liquidity" in low and "money" in low and "market" in low and "invest" in low) or ("market investments" in low):
        return "Liquidity - Money market investments"
    elif "liquidity - money market investments" in low:
        return "Liquidity - Money market investments"

    # FX swap & forward contracts (tolerant)
    elif ("liquidity" in low and "fx" in low and "swap" in low and "forward" in low):
        return "Liquidity - FX swap & forward contracts"
    elif "liquidity - fx swap & forward contracts" in low:
        return "Liquidity - FX swap & forward contracts"

    return ""


def get_liquidity_amount(row_json):
    amount = ""
    if len(row_json.get("By investment category", [])) == 1:
        try:
            raw = row_json["Description"][0].lower().split("ubs")[0].strip()
            parsed = _parse_signed_number_string(raw)
            if parsed == "":
                try:
                    parsed = Decimal(raw.replace(" ", "").replace(',', ''))
                except Exception:
                    parsed = ""
            amount = parsed
        except Exception:
            amount = ""
    elif len(row_json.get("By investment category", [])) == 2:
        amount_str = row_json["By investment category"][-1]
        parsed = _parse_signed_number_string(amount_str)
        if parsed == "":
            try:
                parsed = Decimal(amount_str.replace(" ", "").replace(',', ''))
            except Exception:
                parsed = ""
        if parsed == "":
            try:
                raw = row_json["Description"][0].lower().split("ubs")[0].strip()
                parsed = _parse_signed_number_string(raw)
                if parsed == "":
                    parsed = Decimal(raw.replace(" ", "").replace(',', ''))
            except Exception:
                parsed = ''
        amount = parsed
    return amount


def get_security_name(row_json, position_type):
    desc = row_json.get("Description", [])
    if not desc:
        return ""

    if desc[0] == "ts" or desc[0] == position_type:
        if len(desc) > 2 and not any(char.isdigit() for char in desc[2]):
            return desc[1] + " " + desc[2]
        return desc[1] if len(desc) > 1 else ""
    else:
        if len(desc) > 1 and not any(char.isdigit() for char in desc[1]):
            candidate = (desc[0] + " " + desc[1]).strip()
        else:
            candidate = desc[0].strip()

    try:
        qty, rest = split_leading_quantity_general(candidate)
        if qty is not None and rest:
            candidate = rest
    except Exception:
        pass

    candidate = re.sub(r"\bISIN\b[:\s]*[A-Z0-9\-]+", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", candidate)
    candidate = re.sub(r"\b(as of|as at|dated)\b.*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*\([^)]*\)\s*", " ", candidate)
    candidate = re.sub(r"[\)\(\"\']+", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()

    return candidate


def get_secuitity_name(row_json, position_type):
    return get_security_name(row_json, position_type)
