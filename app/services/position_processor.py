# ============================================================
# FILE: app/services/position_processor.py
# ============================================================

from typing import List, Any
from PIL import Image
from app.utils import *
import math
import numpy as np
import re
from decimal import Decimal


class PositionProcessor:
    
    def __init__(self) -> None:
        # Type hiện tại (được set khi gặp dòng section header)
        self.position_type = None

        # Portfolio no. (set từ tasks.py sau khi tìm được metadata)
        self.portfolio_no = None

        # ✅ FIX: was missing -> caused AttributeError -> skipped ALL rows
        # Valuation date (set từ tasks.py)
        self.valuation_date = ""

    def _format_number_output(self, v):
       
        if v is None:
            return ""

        # Nếu đã là Decimal -> format chuẩn
        if isinstance(v, Decimal):
            return format(v, "f")

        # Convert sang string
        if isinstance(v, (int, float)):
            s = str(v).strip()
        else:
            s = str(v).strip()

        if not s:
            return ""

        # Normalize ký tự minus unicode
        s = s.replace("−", "-").replace("–", "-")

        # Lọc ký tự: giữ số, dấu, space, ',' '.', '()'
        s_clean = re.sub(r"[^0-9\-\+\s,\.()]", "", s).strip()
        if not s_clean:
            return ""

        # Âm theo ngoặc
        neg_by_paren = False
        if "(" in s_clean and ")" in s_clean:
            neg_by_paren = True

        # bỏ ngoặc để parse
        s_no_paren = s_clean.replace("(", "").replace(")", "").strip()
        if not s_no_paren:
            return ""

        # Xác định decimal separator ('.' hay ',') theo vị trí cuối
        dot_pos = s_no_paren.rfind(".")
        comma_pos = s_no_paren.rfind(",")

        decimal_sep = None
        if dot_pos != -1 and comma_pos != -1:
            # cả '.' và ',' cùng xuất hiện -> dấu nào xuất hiện sau thường là decimal
            decimal_sep = "," if comma_pos > dot_pos else "."
        elif comma_pos != -1 and dot_pos == -1:
            # chỉ có ',' -> có thể là thousand sep hoặc decimal sep
            if re.search(r",\d{3}(?:[^\d]|$)", s_no_paren):
                decimal_sep = None  # comma là thousand sep
            else:
                decimal_sep = ","
        else:
            decimal_sep = "."

        # bỏ space
        normalized = s_no_paren.replace(" ", "")

        # Chuẩn hoá theo decimal_sep
        if decimal_sep == ",":
            # '.' là thousand sep, ',' là decimal
            normalized = normalized.replace(".", "")
            normalized = normalized.replace(",", ".")
        else:
            # ',' là thousand sep
            normalized = normalized.replace(",", "")

        # lọc lần cuối
        normalized = re.sub(r"[^0-9\-\+\.]", "", normalized).strip()
        if not normalized:
            return ""

        try:
            dv = Decimal(normalized)
            # nếu ngoặc âm mà số dương -> đổi thành âm
            if neg_by_paren and dv > 0:
                normalized = "-" + normalized.lstrip("+").lstrip("-")
            if normalized.endswith("."):
                normalized = normalized[:-1]
            return normalized
        except Exception:
            return ""

    def _looks_like_section_header_only(self, row_text_tokens: List[str]) -> bool:
        
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
        
        joined = " ".join(row_text_tokens or []).strip()
        low = joined.lower()

        # Hedge funds & private markets - Hedge funds
        if ("hedge funds" in low and "private markets" in low) or \
           "hedge funds & private markets" in low:
            return "Hedge funds & private markets - Hedge funds"

        # Hedge funds treated as Type header
        if re.fullmatch(r"\s*hedge\s+funds\s*", low):
            return "Hedge funds"

        # Others - Structured products & derivatives
        if ("others" in low and "structured products" in low and "derivatives" in low) or \
           "others - structured products" in low:
            return "Others - Structured products & derivatives"

        # Liquidity - FX swap & forward contracts (OCR variations)
        if ("liquidity" in low) and ("fx" in low) and ("swap" in low) and ("forward" in low):
            return "Liquidity - FX swap & forward contracts"

        # Money market investments (OCR variations)
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
        Loại bỏ dòng "rỗng" thực sự.
        Dùng để xử lý case OCR tạo ra dòng thừa (duplicated type line)
        nhưng không có dữ liệu position thực.
        """
        def _nz(s):
            return (str(s).strip() if s is not None else "")

        # nếu có bất kỳ trường quan trọng nào -> không rỗng
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

        # OCR tokens + boxes
        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]

        header_idx_map = {}
        header_box_map = {}

        for col_name in position_columns:
            idx_header = get_index_by_name(col_name, ocr_text)
            header_idx_map[col_name] = idx_header
            if idx_header is not None:
                header_box_map[col_name] = ocr_box[idx_header]
            else:
                header_box_map[col_name] = None

        # Liquidity table headers (bảng Liquidity - Accounts có schema khác)
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
            # Extend row box về lề trái để không bỏ sót token đầu dòng
            yolo_box[0] = 0

            # Lấy index OCR tokens nằm trong row box (threshold 0.8 theo area inner)
            indices, _ = ocr_boxes_inside_yolo(yolo_box, ocr_box, threshold=0.8)

            # Lấy text tokens tương ứng
            result = [ocr_text[i] for i in indices]
            row_list.append({"text": result, "index": indices})

        # Cờ để xử lý trường hợp:
        # - gặp header section -> skip
        # - nhưng vẫn cho phép row ngay sau đó đi qua check header table
        skip_is_header_once = False

        for row in row_list:
            try:
                row_excel = {}

                # Clean: chỉ giữ string, strip, bỏ rỗng
                row["text"] = [e.strip() for e in row["text"] if isinstance(e, str)]
                if not row["text"]:
                    continue

                # Nếu row là header (table header) -> skip
                # Trừ khi skip_is_header_once được set (tức row ngay sau section header)
                if is_header(row["text"]):
                    if skip_is_header_once:
                        skip_is_header_once = False
                    else:
                        continue

                position_type_check = get_position_type({"text": list(row.get("text", []))})
                if not position_type_check:
                    position_type_check = self._detect_position_type_fallback(row.get("text", []))

                # Nếu detect được type -> cập nhật state
                if position_type_check != "":
                    # Nếu dòng này là section header thuần chữ (không có số, không có currency, etc.)
                    # -> chỉ set type và skip parse row
                    if self._looks_like_section_header_only(row.get("text", [])):
                        self.position_type = position_type_check
                        skip_is_header_once = True
                        continue
                    
                    # Nếu row có data (số, currency...) dù có chứa type name
                    # -> set type và tiếp tục parse data
                    self.position_type = position_type_check

                # Nếu vẫn chưa có type -> không parse (chưa biết đang ở section nào)
                if self.position_type is None:
                    continue

                if self.position_type == "Liquidity - Accounts":
                    row_json = {}

                    # Map tokens vào cột (liquidity_account_columns)
                    for col_name in liquidity_account_columns:
                        idx_header = header_idx_map_liq.get(col_name)
                        col_name_box = header_box_map_liq.get(col_name)

                        # Nếu header không tồn tại -> cột rỗng
                        if idx_header is None or col_name_box is None:
                            row_json[col_name] = []
                            continue

                        # OCR tokens của current row
                        ocr_box_of_current_row = [ocr_box[i] for i in row["index"]]
                        ocr_text_of_current_row = [ocr_text[i] for i in row["index"]]

                        # Lấy tokens align theo cột dựa overlap X với header_box
                        aligned_indices = boxes_aligned_in_column_idx(
                            col_name_box,
                            ocr_box_of_current_row,
                            min_overlap_ratio=0.2,
                            center_within=False
                        )
                        row_json[col_name] = [ocr_text_of_current_row[i] for i in aligned_indices]

                    # Nếu không có By investment category -> row không hợp lệ
                    if len(row_json.get("By investment category", [])) == 0:
                        continue

                    # Nếu text By investment category có lẫn type -> remove
                    if self.position_type in row_json["By investment category"]:
                        row_json["By investment category"].remove(self.position_type)

                    # Loại subtotal
                    row_type = get_liquidity_row_type(row_json)
                    if row_type == "subtotal":
                        continue

                    # Parse các trường liquidity
                    currency = get_currency_liquidity_account(row_json)
                    account_no = row_json["Description"][-1] if row_json.get("Description") else ""
                    amount = get_liquidity_amount(row_json)
                    amount_out = self._format_number_output(amount)

                    # Fill schema Excel positions
                    row_excel["Portfolio No."] = self.portfolio_no or ""
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = account_no
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount_out
                    row_excel["Security ID"] = ""

                    # Build security_name từ Description lines (có nhiều noise)
                    desc_lines = row_json.get("Description", [])
                    security_name = ""
                    if desc_lines:
                        last = desc_lines[-1].strip()
                        looks_like_account_or_date = False

                        # Nếu dòng cuối giống account hoặc giống date -> bỏ nó khỏi security name
                        if is_account_no_like(last):
                            looks_like_account_or_date = True
                        if re.search(r"\b\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}\b", last):
                            looks_like_account_or_date = True

                        if looks_like_account_or_date and len(desc_lines) >= 2:
                            candidate_lines = desc_lines[:-1]
                        else:
                            candidate_lines = desc_lines

                        # Join và cleanup
                        joined = " ".join([re.sub(r"\s+", " ", l).strip() for l in candidate_lines if l])
                        joined = re.sub(r"\b\d{3}-\d{6}(?:-[\dA-Z]+)?\b", "", joined)
                        joined = re.sub(r"\b(as of|as at|dated)\b.*", "", joined, flags=re.IGNORECASE)
                        joined = re.sub(r"\b\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}\b", "", joined)
                        joined = re.sub(r"\s+", " ", joined).strip()
                        
                        # Strip leading quantity/numbers from security name
                        # Remove leading decimal numbers (e.g., "0.00", "123.45")
                        joined = re.sub(r'^[\d,\.]+\s+', '', joined)
                        # Remove strange Unicode characters
                        joined = re.sub(r'^[^\w%]+', '', joined)
                        joined = re.sub(r'[）（【】「」『』〈〉《》〔〕]+', '', joined)
                        # Remove leading pure numbers
                        joined = re.sub(r'^(\d+(?:[.,]\d+)?)\s+', '', joined)
                        # Final cleanup
                        joined = re.sub(r"\s+", " ", joined).strip()
                        
                        security_name = joined

                    row_excel["Security name"] = security_name
                    row_excel["Cost price"] = ""
                    row_excel["Market price"] = ""
                    row_excel["Market value"] = ""
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = self.valuation_date or ""

                    extracted_position_data.append(row_excel)

                else:
                    # Nếu type là Hedge funds (bất kỳ variant nào) và row chỉ là header thuần chữ -> skip
                    hedge_fund_types = ["Hedge funds", "Hedge funds & private markets - Hedge funds"]
                    if self.position_type in hedge_fund_types and self._looks_like_section_header_only(row.get("text", [])):
                        skip_is_header_once = True
                        continue
                    
                    # Nếu type là Others - Structured products & derivatives và row chỉ là header -> skip
                    if self.position_type == "Others - Structured products & derivatives" and self._looks_like_section_header_only(row.get("text", [])):
                        skip_is_header_once = True
                        continue

                    row_json = {}

                    # Map tokens vào cột (position_columns)
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

                    # Check row type: subtotal/empty -> skip
                    row_type = get_row_type(row_json)
                    if row_type in ("subtotal", "empty"):
                        continue

                    # Parse fields
                    currency = get_currency_position(row_json)
                    isin = get_isin_position(row_json)

                    amount = get_position_amount(row_json, self.position_type)
                    security_name_raw = get_security_name(row_json, self.position_type)

                    # Nếu security name bắt đầu bằng quantity -> tách qty ra khỏi name
                    extracted_qty, cleaned_name = split_leading_quantity_general(security_name_raw)
                    if extracted_qty is not None:
                        security_name = cleaned_name
                    else:
                        security_name = security_name_raw

                    security_name = re.sub(r"\s+", " ", (security_name or "")).strip()

                    # Cleanup security_name nhiều lớp để tránh noise
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

                    # Nếu amount rỗng thì cố lấy qty từ đầu name theo logic position
                    try:
                        if amount == "" or amount is None:
                            extracted_qty_pos, _cleaned_name_pos = split_leading_quantity_position(security_name_raw)
                            if extracted_qty_pos is not None:
                                amount = extracted_qty_pos
                    except Exception:
                        pass

                    # Parse prices/value
                    cost_price = get_position_cost_price(row_json, self.position_type)
                    market_price = get_market_price(row_json, self.position_type)
                    market_value = get_market_value(row_json, self.position_type)

                    # Format output numbers as string
                    amount_out = self._format_number_output(amount)
                    cost_price_out = self._format_number_output(cost_price)
                    market_price_out = self._format_number_output(market_price)
                    market_value_out = self._format_number_output(market_value)

                    # Nếu row rỗng thực sự -> skip
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

                    # Fill schema Excel
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
                # Nếu 1 row lỗi, bỏ qua row đó, không crash toàn trang
                print(f"[WARN] Position row skipped due to error: {e}")
                continue

        return extracted_position_data
