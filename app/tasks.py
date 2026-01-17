from celery import Celery
from config import settings
import os
import shutil
import re

from app.services.pdf_processor import pdf_processor
from app.services.excel_exporter import excel_exporter
from app.utils import get_client_name_from_text, get_portfolio_no_from_text, get_valuation_date_from_text

# Initialize Celery app
celery_app = Celery(
    "broker_extractor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(task_track_started=True)


def _ensure_clean_task_output_dir(task_id: str) -> str:
    """
    Ensure outputs/<task_id>/ exists and contains ONLY final outputs.
    We remove old artifacts (xlsx/json/png/txt etc.) to guarantee
    the API lists only the 4 Excel files produced by the main pipeline.
    """
    base_dir = "outputs"
    out_dir = os.path.join(base_dir, task_id)

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)

    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _has_portfolio_and_statement(rec_texts) -> bool:
    """
    Check if this OCR page has both:
      - "Portfolio number" (or Portfolio no)
      - "Statement of assets" (valuation date line)
    """
    if not rec_texts:
        return False

    # join tokens (order preserved) for tolerant matching
    flat = " ".join([str(x) for x in rec_texts if x is not None]).strip()
    low = re.sub(r"\s+", " ", flat.lower()).strip()

    has_portfolio = ("portfolio number" in low) or ("portfolio no" in low) or ("portfolio no." in low)
    has_statement = ("statement of assets" in low)

    return has_portfolio and has_statement


@celery_app.task(bind=True)
def process_pdf_task(self, pdf_path: str):
    """
    Celery task to process a PDF file.
    Workflow:
    1. Convert PDF pages to images.
    2. Perform OCR once per page.
    3. Classify page type from OCR text.
    4. Extract structured info (position / transaction) using improved logic.
    5. Export ONLY final outputs to 4 Excel files in outputs/<task_id>/.
    """
    self.update_state(state='PROGRESS', meta={'current_step': 'Starting PDF processing', 'pdf_path': pdf_path})

    try:
        # 1. Convert PDF pages to images
        self.update_state(state='PROGRESS', meta={'current_step': 'Converting PDF to images'})
        page_images = pdf_processor.pdf_to_images(pdf_path)

        extracted_data_list = {"position": [], "transaction": {"trade": [], "fx_tf": [], "other": []}}

        # ✅ NEW: metadata fallback scan across pages (no longer only first page)
        metadata_set = False
        client_name = ""
        portfolio_no = ""
        valuation_date = ""

        for i, image in enumerate(page_images):
            self.update_state(
                state='PROGRESS',
                meta={'current_step': f'Processing page {i+1}/{len(page_images)}'}
            )

            # 2. Perform OCR ONCE
            ocr_result = pdf_processor.perform_ocr(image)

            # Get rec_texts safely
            rec_texts = []
            if ocr_result and ocr_result[0] and isinstance(ocr_result[0], dict):
                rec_texts = ocr_result[0].get("rec_texts", []) or []

            # ✅ Try set metadata as soon as we find a page with both markers
            if (not metadata_set) and _has_portfolio_and_statement(rec_texts):
                try:
                    # client name: use token list directly (your rule between markers)
                    client_name = get_client_name_from_text(rec_texts)

                    # portfolio/date: safe on flattened text
                    full_text = " ".join(rec_texts) if rec_texts else ""
                    portfolio_no = get_portfolio_no_from_text(full_text)
                    valuation_date = get_valuation_date_from_text(full_text)

                    # set into processors
                    pdf_processor.transaction_processor.client_name = client_name
                    pdf_processor.postion_processor.portfolio_no = portfolio_no
                    pdf_processor.postion_processor.valuation_date = valuation_date

                    metadata_set = True
                except Exception:
                    # do not block pipeline
                    pass

            # 3. Classify based on OCR text (NO extra OCR call)
            page_type = pdf_processor.classify_page(ocr_result)

            # 4. Extract relevant information
            extracted_info = pdf_processor.extract_info(image, ocr_result, page_type)

            if not extracted_info:
                continue

            if page_type == "position":
                if isinstance(extracted_info, list):
                    extracted_data_list["position"].extend(extracted_info)
            elif page_type == "transaction":
                if isinstance(extracted_info, dict):
                    extracted_data_list["transaction"]["trade"].extend(extracted_info.get("trade_info", []))
                    extracted_data_list["transaction"]["fx_tf"].extend(extracted_info.get("fx_tf_info", []))
                    extracted_data_list["transaction"]["other"].extend(extracted_info.get("other_info", []))
            else:
                continue

        # ✅ If we never found the markers anywhere, ensure processors still have safe defaults
        if not metadata_set:
            try:
                pdf_processor.transaction_processor.client_name = ""
                # keep portfolio/valuation as empty to avoid wrong data
                pdf_processor.postion_processor.portfolio_no = ""
                pdf_processor.postion_processor.valuation_date = ""
            except Exception:
                pass

        # 5. Export data to Excel (ONLY 4 files)
        self.update_state(state='PROGRESS', meta={'current_step': 'Exporting data to Excel'})

        task_id = self.request.id if hasattr(self, "request") else "unknown_task"
        output_dir = _ensure_clean_task_output_dir(task_id)

        excel_exporter.export_to_excel(extracted_data_list, output_dir)

        self.update_state(
            state='PROGRESS',
            meta={'current_step': 'Finished processing', 'excel_folder': output_dir}
        )

        return {"status": "success", "message": "PDF processed successfully", "excel_folder": output_dir}

    except Exception as e:
        self.update_state(state='FAILURE', meta={'current_step': 'Error during processing', 'error': str(e)})
        return {"status": "failure", "message": "Error during processing", "error": str(e)}
