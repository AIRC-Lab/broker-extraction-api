import os
import io
from PIL import Image
import cv2
from pypdf import PdfReader
from paddleocr import PaddleOCR
from ultralytics import YOLO
from pdf2image import convert_from_path
from app.utils import classify_page_type
from .position_processor import PositionProcessor
from .transaction_processor import TransactionProcessor
import numpy as np
class PDFProcessor:
    def __init__(self):
        # Initialize PaddleOCR once to avoid repeated loading
        # lang='en' for English, use_gpu=False for CPU only
        # For production, consider setting use_gpu=True if a GPU is available
        self.ocr = PaddleOCR(
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
            use_doc_orientation_classify=False, # Disables document orientation classification model via this parameter
            use_doc_unwarping=False, # Disables text image rectification model via this parameter
            use_textline_orientation=False, # Disables text line orientation classification model via this parameter
        )
        self.yolo = YOLO("app/weights/yolo_broker_line_detect.pt")
        self.postion_processor = PositionProcessor()
        self.transaction_processor = TransactionProcessor()

    def pdf_to_images(self, pdf_path: str) -> list[Image.Image]:
        """
        Converts each page of a PDF file into a PIL Image object using pdf2image.
        Requires poppler-utils to be installed on the system.
        """
        try:
            images = convert_from_path(pdf_path)
            print(f"[DEBUG] Converted {len(images)} pages from PDF to images.")
            return images
        except Exception as e:
            print(f"Error converting PDF to images: {e}")
            raise

    def classify_page(self, image: Image.Image) -> str:
        """
        Classifies a page as 'position' or 'transaction' based on its content.
        This is a placeholder and would involve more sophisticated logic (e.g., keyword spotting, layout analysis).
        For demonstration, it will perform OCR on the image and look for keywords.
        """
        # Perform OCR on the image to get text for classification
        ocr_result = self.perform_ocr(image)
        full_text = " ".join(ocr_result[0]["rec_texts"])
        page_type = classify_page_type(full_text)
        print(f"[DEBUG] Classified page as: {page_type}")
        return page_type

    def perform_ocr(self, image: Image.Image) -> list:
        """
        Performs OCR on an image using PaddleOCR and returns the raw OCR result.
        """
        # Convert PIL Image to numpy array for PaddleOCR
        img_array = np.array(image)
        ocr_result = self.ocr.ocr(img_array)
        ocr_box = ocr_result[0]["rec_boxes"]
        ocr_text = ocr_result[0]["rec_texts"]
        if "Description" in ocr_text:
            des_idx = ocr_text.index("Description")
            amount_sep = ocr_box[des_idx]
            cv2.rectangle(img_array, (amount_sep[0]-2, 0), (amount_sep[0]-1, img_array.shape[1]), color=(255, 0, 0), thickness=1)
            result = self.ocr.ocr(img_array)
        else:
            result = ocr_result
        print(f"[DEBUG] Performed OCR. Found {len(result[0]) if result and result[0] else 0} text blocks.")
        return result

    def extract_info(self, image: Image.Image, ocr_result: list, page_type: str) -> dict:
        """
        Extracts structured information from the OCR result based on page type.
        This is a placeholder for complex parsing logic.
        """        
        # Example: Simple extraction based on page type and OCR results
        if page_type == 'position':
            extracted_data = self.postion_processor.process(self.yolo, image, ocr_result)
        elif page_type == 'transaction':
            extracted_data = self.transaction_processor.process(self.yolo, image, ocr_result)
        else:
            extracted_data = {}
        print(f"[DEBUG] Extracted info for {page_type} page.")
        return extracted_data

pdf_processor = PDFProcessor()