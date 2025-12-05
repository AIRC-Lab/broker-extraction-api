from typing import List, Any
from PIL import Image
from app.utils import *
import math
import numpy as np
class TransactionProcessor:
    """A processor for extracting and refining Transactional information 
    from OCR results using a YOLO object detection model."""

    def __init__(self) -> None:
        """Initialize the TransactionProcessor instance."""
        # Add initialization parameters here if needed in the future
        pass

    def process(
        self, 
        yolo_model: Any, 
        image: Image.Image, 
        ocr_result: List[dict]
    ) -> List[dict]:
        """
        Process an image and its OCR results to refine object Transactions.

        Args:
            yolo_model (Any): The YOLO model instance used for object detection.
            image (Image.Image): The input image to process.
            ocr_result (List[dict]): The OCR-detected text boxes and metadata.

        Returns:
            List[dict]: A list of processed transactional data combining 
                        detection and OCR information.
        """
        detection_result = yolo_model.predict(image)[0].boxes.xyxy.tolist()
        ceil_det_box = [[math.ceil(x) for x in yolo_box] for yolo_box in detection_result]
        sorted_det_boxes = sorted(ceil_det_box, key=lambda box: box[1])
        img_array = np.array(image)
        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]
        row_list = []
        for yolo_box in sorted_det_boxes:
            indices, kept = ocr_boxes_inside_yolo(yolo_box,ocr_box,threshold=0.9)
            result = [ocr_text[i] for i in indices]
            row_list.append({"text":result,"index": indices})
        trade_information = []
        dividend_information = []
        fx_tf_information = []
        other_information = []
        for row in row_list:
            try:
                row["text"] = [e.strip() for e in row["text"]]
                if is_header(row["text"]):
                    continue
                row_json = {}
                for col_name in transaction_columns:
                    col_name_box = ocr_box[get_index_by_name(col_name,ocr_text)]
                    ocr_box_of_current_row = [ocr_box[i] for i in row["index"]]
                    ocr_text_of_current_row  = [ocr_text[i] for i in row["index"]]
                    algined_indices = boxes_aligned_in_column_idx(col_name_box,ocr_box_of_current_row,min_overlap_ratio=0.2,center_within=False)
                    row_json[col_name]= [ocr_text_of_current_row[i] for i in algined_indices]

                row_excel = {}
                transaction_type = get_transaction_type(row_json)
                if transaction_type in ["Purchase", "Sale"]:
                    isin = get_isin(row_json)
                    trade_date, settlement_date= get_trade_settlement_date(row_json)
                    currency = get_currency(row_json)
                    security_name = remove_start_number(row_json["Custody account"][0]+ " " + row_json["Custody account"][1])
                    quantity = get_quantity(row_json)
                    account_no = get_account_no(row_json)
                    foreign_unit_price = get_foreign_unit_price(row_json, transaction_type)
                    # foreign_gross_consideration = get_foreign_gross_consideration(row_json, transaction_type)
                    # foreign_net_consideration = foreign_gross_consideration
                    foreign_gross_consideration, foreign_net_consideration, accrued_interest = get_foreign_gross_net_consideration(row_json,transaction_type)
                    net_consideration = foreign_net_consideration if accrued_interest!="" else ""
                    row_excel["Client name"] = "GINKGO TREE GLOBAL ALLOCATION FUND"
                    row_excel["Name/ Security"] = security_name
                    row_excel["Securities ID"] =  isin
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
                    row_excel["Foreign `Transaction` Fee"]= ""
                    trade_information.append(row_excel)
                elif transaction_type=="UBS Call Deposit":
                    isin = get_isin(row_json)
                    trade_date, settlement_date= get_trade_settlement_date(row_json)
                    currency = get_currency(row_json)
                    row_excel["Client name"] = "GINKGO TREE GLOBAL ALLOCATION FUND"
                    row_excel["Description"] = row_json["Booking text"][0].strip()
                    row_excel["Securities ID"] =  isin
                    row_excel["Transaction type"] = transaction_type
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Currency"] = ""
                    row_excel["Quantity"] = ""
                    row_excel["Foreign Unit Price/ Interest rate"] = ""
                    foreign_gross_consideration, foreign_net_consideration, accrued_interest = get_foreign_gross_net_consideration(row_json,transaction_type)
                    row_excel["Foreign Gross Amount/Interest"] = foreign_gross_consideration
                    row_excel["Tax rate (%)"] = ""
                    row_excel["Foreign Net Amount"] = row_excel["Foreign Gross Amount/Interest"]
                    row_excel["Payment mode"] = ""
                    row_excel["Account no."] = get_account_no(row_json)
                    row_excel["Exrate to GST"] = ""
                    row_excel["Amount (SGD)"] = ""
                    other_information.append(row_excel)
                elif transaction_type=="FX Forward":
                    row_excel = {}
                    isin = get_isin(row_json)
                    trade_date, settlement_date= get_trade_settlement_date(row_json)
                    currency = get_currency(row_json)
                    row_excel["Client name"] = "GINKGO TREE GLOBAL ALLOCATION FUND"
                    row_excel["Transaction type"] = transaction_type
                    row_excel["Trade date"] = trade_date
                    row_excel["Settlement date"] = settlement_date
                    row_excel["Rate"] = row_json["Cost/Purchase price"][0].strip()
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
        return {"trade_info": trade_information, "fx_tf_info": fx_tf_information, "other_info":other_information}

