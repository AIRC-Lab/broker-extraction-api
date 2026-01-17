from typing import List, Tuple
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


def get_client_name_from_text(text: str):
    """
    Heuristic client name extraction from page header text.
    Prefer the line immediately after a 'Portfolio number' occurrence (common layout).
    Otherwise prefer a line containing 'FUND' (case-insensitive), then an uppercase short line.
    """
    if not text:
        return ""

    # normalize whitespace
    text_norm = re.sub(r"\s+", " ", text or "").strip()
    # split into lines when available; if text is a single long line (from tasks.py),
    # also create candidate fragments by splitting on common separators.
    raw_lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if len(raw_lines) <= 1:
        # create fragments from the single long line
        frags = re.split(r"\s{2,}|\s-\s|\s\|\s|\s:\s|\s/\s|\s—\s|\s–\s", text_norm)
        lines = [f.strip() for f in frags if f.strip()]
        # ensure we also keep the original long line as fallback
        if text_norm and text_norm not in lines:
            lines.insert(0, text_norm)
    else:
        lines = [re.sub(r"\s+", " ", l).strip() for l in raw_lines if l.strip()]

    def sanitize_name(ln: str) -> str:
        s = ln.strip()
        s = re.sub(r'page\s*\d+\s*(of\s*\d+)?', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\b(as of|as at|dated)\b.*", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", s)
        s = s.strip(' -:\u2014')
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def is_noise(ln: str) -> bool:
        if not ln:
            return True
        low = ln.lower()
        noise = [
            'statement', 'portfolio', 'valuation', 'valued', 'page', 'of', 'accounts',
            'detailed positions', 'transaction list', 'by investment category', 'liquidity',
            'last purchase', 'statement of assets', 'report', 'dated', 'as of'
        ]
        for t in noise:
            if t in low:
                return True
        # very long lines with many digits are likely header block
        if any(ch.isdigit() for ch in ln) and len(ln.split()) > 10:
            return True
        return False

    # gather candidate lines (single lines, not too long)
    candidates = []
    for ln in lines:
        ln_s = ln.strip()
        if not ln_s:
            continue
        # ignore purely numeric or account-like lines
        if is_account_no_like(ln_s) or re.fullmatch(r"[\d\s\-\./]+", ln_s):
            continue
        candidates.append(ln_s)

    # If tasks.py provided a flattened full_text, try targeted extraction around 'portfolio'
    low_text = text_norm.lower()
    if 'portfolio' in low_text and (not candidates or len(candidates) == 1 and len(candidates[0].split()) > 10):
        # look for 'portfolio' and take preceding fragment as candidate
        m = re.search(r"(.{0,200})\bportfolio\b", low_text)
        if m:
            before = text_norm[:m.start(0)].strip()
            parts = re.split(r"\s{2,}|\s-\s|\s\|\s|\s:\s", before)
            for p in reversed(parts):
                p = p.strip()
                if not p:
                    continue
                if any(ch.isdigit() for ch in p) and len(p.split()) > 6:
                    continue
                if is_account_no_like(p):
                    continue
                candidates.insert(0, p)
                break

    if not candidates:
        return sanitize_name(lines[0]) if lines else ""

    # score candidates: prefer short, alphabetic, contains 'fund' or uppercase name
    def score(ln: str) -> int:
        words = ln.split()
        wlen = len(words)
        digits = sum(ch.isdigit() for ch in ln)
        digit_penalty = 10 if digits > 0 else 0
        noise_penalty = 5 if is_noise(ln) else 0
        fund_bonus = -3 if 'fund' in ln.lower() else 0
        uppercase_bonus = -1 if ln == ln.upper() and 2 <= wlen <= 8 else 0
        return wlen * 2 + digit_penalty + noise_penalty + fund_bonus + uppercase_bonus

    best = min(candidates, key=lambda x: score(x))
    best = sanitize_name(best)
    # ensure result is not an overly long paragraph; if so, pick shortest candidate
    if len(best.split()) > 12:
        shortest = min(candidates, key=lambda x: len(x.split()))
        best = sanitize_name(shortest)

    return best
    


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

    # parse using Decimal-aware helper to preserve precision and separators
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
    Examples:
      "408 156.10" -> 408156.10
      "-437 212.32" -> -437212.32
      "(437 212.32)" -> -437212.32
      "289792000" -> 289792000
    """
    if not num_str:
        return ""
    s = str(num_str).strip()

    # normalize weird minus chars if OCR returns them
    s = s.replace("−", "-").replace("–", "-")

    # parentheses as negative (accounting style)
    neg_by_paren = False
    if "(" in s and ")" in s:
        neg_by_paren = True

    # keep only sign, digits, dot, comma, space, parentheses
    s_clean = re.sub(r"[^0-9\-\+\s,\.()]", "", s).strip()
    if not s_clean:
        return ""

    # remove parentheses for parsing
    s_no_paren = s_clean.replace("(", "").replace(")", "")

    # Decide decimal separator: if both '.' and ',' present, assume the rightmost symbol is decimal separator
    dot_pos = s_no_paren.rfind('.')
    comma_pos = s_no_paren.rfind(',')
    decimal_sep = None
    thousand_seps = [' ']
    if dot_pos != -1 and comma_pos != -1:
        if comma_pos > dot_pos:
            decimal_sep = ','
        else:
            decimal_sep = '.'
    elif comma_pos != -1 and dot_pos == -1:
        # ambiguous: could be decimal comma or thousand separator. Heuristic: if comma followed by 3 digits, treat as thousand sep
        m = re.search(r",\d{3}(?:[^\d]|$)", s_no_paren)
        if m:
            decimal_sep = None
        else:
            decimal_sep = ','
    else:
        decimal_sep = '.'

    # remove thousand separators and normalize decimal separator to dot
    normalized = s_no_paren
    # remove spaces always
    normalized = normalized.replace(' ', '')
    if decimal_sep == ',':
        # remove dots (thousand) if any, replace comma with dot
        normalized = normalized.replace('.', '')
        normalized = normalized.replace(',', '.')
    else:
        # decimal is dot: remove commas
        normalized = normalized.replace(',', '')

    # final cleanup: keep only digits, sign, dot
    normalized = re.sub(r"[^0-9\-\+\.]", "", normalized)

    try:
        val = Decimal(normalized)
        if neg_by_paren and val > 0:
            val = -val
        return val
    except (InvalidOperation, ValueError):
        return ""


def _compact_lower(s: str) -> str:
    """lower + remove all whitespace for OCR-tolerant matching"""
    if not s:
        return ""
    return re.sub(r"\s+", "", s.lower()).strip()


def _extract_ccy_amount_pairs(lines: List[str]):
    """
    Fallback: scan all lines and collect currency-amount pairs like:
      EUR 408156.1
      USD -437212.32
    Return list of tuples (CCY, amount_float)
    """
    pairs = []
    if not lines:
        return pairs

    for ln in lines:
        if not ln:
            continue
        t = re.sub(r"\s+", " ", str(ln)).strip()
        if not t:
            continue

        # find ALL occurrences in the same line (sometimes both appear)
        for m in re.finditer(r"\b([A-Z]{3})\s+([+\-]?\d[\d\s,\.()\-]*)", t):
            ccy = (m.group(1) or "").strip()
            amt_raw = (m.group(2) or "").strip()
            amt = _parse_signed_number_string(amt_raw)
            if ccy and isinstance(amt, (int, float, Decimal)):
                pairs.append((ccy, amt))

    # dedupe while keeping order
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
    """
    Extract (currency, amount) from a line like:
      "You bought EUR 408 156.10"
      "You sold  USD -437 212.32"
    verb: "bought" or "sold"
    """
    if not lines:
        return "", ""

    verb_key = f"you{verb}"  # compact key: "youbought" / "yousold"

    # ✅ FIX: prebuild regex chunk OUTSIDE f-string expression
    verb_regex = "".join([ch + r"\s*" for ch in verb])

    # 1) try find explicit verb line (OCR tolerant)
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
            # enforce negative if OCR lost sign
            if amt > 0:
                amt = -amt

        return cur, amt

    # 2) fallback: scan currency/amount pairs from all lines
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
    """
    robust Rate fallback for FX Forward.
    """
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

    # ✅ FIX: OCR hay nhầm '.' thành ',' trong account number
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
    """
    Split leading quantity from a security line like:
      '100 000 4.625% Medium Term Notes Toyota Motor Credit Corp.'
    """
    if not text or not isinstance(text, str):
        return None, text

    s = text.strip()
    if not s or not s[0].isdigit():
        return None, s

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
    """
    Handle position Security name like:
      '2 000 Shs Air Liquide SA (AI)'
    """
    if not text or not isinstance(text, str):
        return None, text

    s = re.sub(r"\s+", " ", text).strip()
    if not s:
        return None, s

    if re.match(r"^\d+(\.\d+)?\s*%", s):
        return None, s

    if not s[0].isdigit():
        return None, s

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


# -----------------------------
# robust filters for TRADE "Name/ Security"
# -----------------------------
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
    # remove leading quantity if present (e.g., '100 000 Foo Bar')
    try:
        qty, rest = split_leading_quantity_general(name)
        if qty is not None and rest:
            name = rest
    except Exception:
        pass

    # remove common account tokens, trailing dates, ISIN tokens and stray punctuation
    name = re.sub(r"\bISIN\b[:\s]*[A-Z0-9\-]+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", name)
    name = re.sub(r"\b(as of|as at|dated)\b.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*\([^)]*\)\s*", " ", name)  # remove parenthesized qualifiers
    name = re.sub(r"[\)\(\"\']+", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


# ==========================================================
# ✅ NEW: ONLY for OTHER (UBS Call Deposit) - keep minus sign
# ==========================================================
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
    """
    For OTHER (UBS Call Deposit): preserve sign for amounts.
    - Prefer reading from 'Transaction value' last cell (same as old logic)
    - Parse signed float, keep '-' or parentheses if present
    - If OCR lost '-', use booking_text heuristic:
        Reduction / Repayment  -> negative
        Interest Cap.         -> positive
    Return: (gross, net, accrued_interest)
    """
    booking_text = " ".join(row_json.get("Booking text", [])).strip()
    booking_text = booking_text.replace("\n", " ").strip()
    bt_low = booking_text.lower()

    txv = row_json.get("Transaction value", [])

    # choose values similarly to old logic (but we keep sign)
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

    # heuristic sign fix ONLY for other:
    # reduction/repayment typically outflow -> negative
    should_be_negative = ("reduction" in bt_low) or ("repayment" in bt_low)
    should_be_positive = ("interest cap" in bt_low) or ("interest" in bt_low)

    # If OCR lost sign (we detect no sign hint) and value is positive, apply heuristic
    if isinstance(gross_val, (int, float, Decimal)) and gross_val > 0:
        if should_be_negative and (not _is_negative_hint_text(gross_raw)):
            gross_val = -gross_val
    if isinstance(net_val, (int, float, Decimal)) and net_val > 0:
        if should_be_negative and (not _is_negative_hint_text(net_raw)):
            net_val = -net_val

    # if heuristic says positive, ensure positive
    if isinstance(gross_val, (int, float, Decimal)) and gross_val < 0 and should_be_positive and (not should_be_negative):
        gross_val = abs(gross_val)
    if isinstance(net_val, (int, float, Decimal)) and net_val < 0 and should_be_positive and (not should_be_negative):
        net_val = abs(net_val)

    # normalize empty
    if gross_val == "":
        gross_val = Decimal('0')
    if net_val == "":
        net_val = Decimal('0')

    return gross_val, net_val, accrued_interest


# -----------------------------
# Position helpers
# -----------------------------
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
        # Use Decimal-aware parser to respect comma/dot decimal separators
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
        # find numeric token (including commas/dots/percent)
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

    # remove leading quantity tokens (e.g., '2 000 Shs Foo')
    try:
        qty, rest = split_leading_quantity_general(candidate)
        if qty is not None and rest:
            candidate = rest
    except Exception:
        pass

    # strip trailing account/date/ISIN tokens and parenthesis
    candidate = re.sub(r"\bISIN\b[:\s]*[A-Z0-9\-]+", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", candidate)
    candidate = re.sub(r"\b(as of|as at|dated)\b.*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*\([^)]*\)\s*", " ", candidate)
    candidate = re.sub(r"[\)\(\"\']+", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()

    return candidate


def get_secuitity_name(row_json, position_type):
    return get_security_name(row_json, position_type)
