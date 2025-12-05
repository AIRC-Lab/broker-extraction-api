from typing import List, Any
from PIL import Image
from app.utils import *
import math
import numpy as np

class PositionProcessor:
    """A processor for extracting and refining positional information 
    from OCR results using a YOLO object detection model."""

    def __init__(self) -> None:
        """Initialize the PositionProcessor instance."""
        self.position_type = None
        # Add initialization parameters here if needed in the future
        pass

    def process(
        self, 
        yolo_model: Any, 
        image: Image.Image, 
        ocr_result: List[dict]
    ) -> List[dict]:
        """
        Process an image and its OCR results to refine object positions.

        Args:
            yolo_model (Any): The YOLO model instance used for object detection.
            image (Image.Image): The input image to process.
            ocr_result (List[dict]): The OCR-detected text boxes and metadata.

        Returns:
            List[dict]: A list of processed positional data combining 
                        detection and OCR information.
        """
        detection_result = yolo_model.predict(image)[0].boxes.xyxy.tolist()
        ceil_det_box = [[math.ceil(x) for x in yolo_box] for yolo_box in detection_result]
        sorted_det_boxes = sorted(ceil_det_box, key=lambda box: box[1])
        img_array = np.array(image)
        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]
        row_list = []
        extracted_position_data = []
        for yolo_box in sorted_det_boxes:
            yolo_box[0] = 0
            indices, kept = ocr_boxes_inside_yolo(yolo_box,ocr_box,threshold=0.8)
            result = [ocr_text[i] for i in indices]
            row_list.append({"text":result,"index": indices})

        for row in row_list:
            try:
                row_excel = {}
                row["text"] = [e.strip() for e in row["text"]]
                if is_header(row["text"]):
                    continue
                position_type_check = get_position_type(row)
                if position_type_check!="":
                    self.position_type = position_type_check
                if self.position_type is None:
                    continue
                if self.position_type=="Liquidity - Accounts":
                    row_json = {}
                    for col_name in liquidity_account_columns:
                        col_name_box = ocr_box[get_index_by_name(col_name,ocr_text)]
                        ocr_box_of_current_row = [ocr_box[i] for i in row["index"]]
                        ocr_text_of_current_row  = [ocr_text[i] for i in row["index"]]
                        algined_indices = boxes_aligned_in_column_idx(col_name_box,ocr_box_of_current_row,min_overlap_ratio=0.2,center_within=False)
                        row_json[col_name]= [ocr_text_of_current_row[i] for i in algined_indices]
                    if len(row_json["By investment category"])==0:
                        continue
                    if self.position_type in row_json["By investment category"]:
                        row_json["By investment category"].remove(self.position_type)
                    
                    row_type = get_liquidity_row_type(row_json)
                    if row_type=="subtotal":
                        continue
                    print("[DEBUG]==================================")
                    print(row_json)
                    currency = get_currency_liquidity_account(row_json)
                    account_no = row_json["Description"][-1]
                    amount = get_liquidity_amount(row_json)
                    row_excel["Portfolio No."] = "546-880515-01"
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = account_no
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount
                    row_excel['Security ID'] = ""
                    row_excel["Secuitity name"] = ""
                    row_excel["Cost price"] = ""
                    row_excel["Market price"] = ""
                    row_excel["Market value"] = ""
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = ""
                    extracted_position_data.append(row_excel)
                else:
                    row_json = {}
                    for col_name in position_columns:
                        col_name_box = ocr_box[get_index_by_name(col_name,ocr_text)]
                        ocr_box_of_current_row = [ocr_box[i] for i in row["index"]]
                        ocr_text_of_current_row  = [ocr_text[i] for i in row["index"]]
                        algined_indices = boxes_aligned_in_column_idx(col_name_box,ocr_box_of_current_row,min_overlap_ratio=0.2,center_within=False)
                        row_json[col_name]= [ocr_text_of_current_row[i] for i in algined_indices]
                    row_type = get_row_type(row_json)
                    if row_type=="subtotal" or row_type=="empty":
                        continue
                    print("[DEBUG]==================================")
                    print(row_json)
                    currency = get_currency_postion(row_json)
                    isin = get_isin_position(row_json)
                    # secuitity_name, amount = get_position_secuitity_name_amount(row_json, self.position_type)
                    amount = get_position_amount(row_json, self.position_type)
                    secuitity_name = get_secuitity_name(row_json, self.position_type)
                    cost_price = get_position_cost_price(row_json, self.position_type)
                    market_price = get_market_price(row_json, self.position_type)
                    market_value = get_market_value(row_json, self.position_type)

                    row_excel["Portfolio No."] = "546-880515-01"
                    row_excel["Type"] = self.position_type
                    row_excel["Account No"] = ""
                    row_excel["Currency"] = currency
                    row_excel["Quantity/ Amount"] = amount
                    row_excel['Security ID'] = isin
                    row_excel["Secuitity name"] = secuitity_name
                    row_excel["Cost price"] = cost_price
                    row_excel["Market price"] = market_price
                    row_excel["Market value"] = market_value
                    row_excel["Accrued interest"] = ""
                    row_excel["Valuation date"] = "03/31/25"
                    extracted_position_data.append(row_excel)
            except:
                continue
        return extracted_position_data