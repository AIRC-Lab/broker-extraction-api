import os
import io
from PIL import Image
import cv2
from pypdf import PdfReader
from paddleocr import PaddleOCR
from ultralytics import YOLO
from pdf2image import convert_from_path
import numpy as np

from app.utils import classify_page_type
from .position_processor import PositionProcessor
from .transaction_processor import TransactionProcessor


class PDFProcessor:
    def __init__(self):
        self.ocr = PaddleOCR(
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
            device="gpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

        self.yolo = YOLO("app/weights/yolo_broker_line_detect.pt")

        self.postion_processor = PositionProcessor()
        self.transaction_processor = TransactionProcessor()

    def pdf_to_images(self, pdf_path: str) -> list[Image.Image]:
        
        try:
            images = convert_from_path(pdf_path)
            print(f"[DEBUG] Converted {len(images)} pages from PDF to images.")
            return images
        except Exception as e:
            print(f"[ERROR] Error converting PDF to images: {e}")
            raise

    def classify_page(self, ocr_result: list) -> str:
       
        try:
            if not ocr_result or not ocr_result[0] or "rec_texts" not in ocr_result[0]:
                return "other"

            # Nối toàn bộ token OCR thành chuỗi lớn để classify bằng keyword
            full_text = " ".join(ocr_result[0]["rec_texts"])
            page_type = classify_page_type(full_text)
            print(f"[DEBUG] Classified page as: {page_type}")
            return page_type
        except Exception as e:
            print(f"[WARN] classify_page failed: {e}")
            return "other"

    def perform_ocr(self, image: Image.Image) -> list:
       
        img_array = np.array(image)
        try:
            result = self.ocr.ocr(img_array)

            # Log số text blocks (tuỳ version paddleocr: result[0] có thể list hoặc dict)
            print(f"[DEBUG] Performed OCR. Found {len(result[0]) if result and result[0] else 0} text blocks.")
            return result
        except Exception as e:
            print(f"[ERROR] OCR failed: {e}")
            raise

    def extract_info(self, image: Image.Image, ocr_result: list, page_type: str):
        try:
            if page_type == 'position':
                extracted_data = self.postion_processor.process(self.yolo, image, ocr_result)
            elif page_type == 'transaction':
                extracted_data = self.transaction_processor.process(self.yolo, image, ocr_result)
            else:
                extracted_data = {}

            print(f"[DEBUG] Extracted info for {page_type} page.")
            return extracted_data
        except Exception as e:
            # Không crash toàn pipeline nếu 1 trang lỗi
            print(f"[WARN] extract_info failed for page_type={page_type}: {e}")
            return {}


# Instance dùng chung
pdf_processor = PDFProcessor()
