from celery import Celery
from config import settings
import os
from app.services.pdf_processor import pdf_processor
from app.services.excel_exporter import excel_exporter


# Initialize Celery app
celery_app = Celery(
    "broker_extractor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(task_track_started=True)


@celery_app.task(bind=True)
def process_pdf_task(self, pdf_path: str):
    """
    Celery task to process a PDF file.
    This task will orchestrate the PDF processing workflow:
    1. Convert PDF pages to images.
    2. Classify each page (position or transaction).
    3. Perform OCR using PaddleOCR.
    4. Extract relevant information.
    5. Export data to an Excel file.
    """
    self.update_state(
        state='PROGRESS',
        meta={'current_step': 'Starting PDF processing', 'pdf_path': pdf_path}
    )

    try:
        # 1. Convert PDF pages to images
        self.update_state(state='PROGRESS', meta={'current_step': 'Converting PDF to images'})
        # NOTE: The pdf_to_images method in pdf_processor.py currently returns dummy images.
        # In a real deployment, you would need to install poppler-utils and pdf2image
        # and modify pdf_to_images to use convert_from_path.

        page_images = pdf_processor.pdf_to_images(pdf_path)

        extracted_data_list = {"position": [], "transaction": {"trade": [], "fx_tf": [], "other": []}}

        for i, image in enumerate(page_images):
            self.update_state(
                state='PROGRESS',
                meta={'current_step': f'Processing page {i+1}/{len(page_images)}'}
            )

            # 2. Classify each page
            page_type = pdf_processor.classify_page(image)

            # 3. Perform OCR
            ocr_result = pdf_processor.perform_ocr(image)

            # 4. Extract relevant information
            extracted_info = pdf_processor.extract_info(image, ocr_result, page_type)

            if len(extracted_info) == 0:
                continue

            if page_type == "position":
                extracted_data_list["position"].extend(extracted_info)
            else:
                extracted_data_list["transaction"]["trade"].extend(extracted_info["trade_info"])
                extracted_data_list["transaction"]["fx_tf"].extend(extracted_info["fx_tf_info"])
                extracted_data_list["transaction"]["other"].extend(extracted_info["other_info"])

        # 5. Export data to an Excel file
        self.update_state(state='PROGRESS', meta={'current_step': 'Exporting data to Excel'})
        # Export outputs to outputs/{task_id}/*.xlsx

        task_id = self.request.id if hasattr(self, "request") else "unknown_task"
        output_excel_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs", task_id)
        excel_exporter.export_to_excel(extracted_data_list, output_excel_path)

        self.update_state(
            state='PROGRESS',
            meta={'current_step': 'Finished processing', 'excel_file_path': output_excel_path}
        )

        return {
            "status": "success",
            "message": "PDF processed successfully",
            "excel_file_path": output_excel_path
        }

    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={'current_step': 'Error during processing', 'error': str(e)}
        )
        return {"status": "failure", "message": "Error during processing"}
        # raise # Re-raise the exception so Celery can handle it properly
