from celery import Celery
from config import settings
import os
import shutil
import re

from app.services.pdf_processor import pdf_processor
from app.services.excel_exporter import excel_exporter
from app.utils import get_client_name_from_text, get_portfolio_no_from_text, get_valuation_date_from_text

celery_app = Celery(
    "broker_extractor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(task_track_started=True)


def _ensure_clean_task_output_dir(task_id: str) -> str:
    base_dir = "outputs"
    out_dir = os.path.join(base_dir, task_id)

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)

    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _has_portfolio_and_statement(rec_texts) -> bool:
    if not rec_texts:
        return False

    flat = " ".join([str(x) for x in rec_texts if x is not None]).strip()
    low = re.sub(r"\s+", " ", flat.lower()).strip()

    has_portfolio = ("portfolio number" in low) or ("portfolio no" in low) or ("portfolio no." in low)
    has_statement = ("statement of assets" in low)

    return has_portfolio and has_statement


@celery_app.task(bind=True)
def process_pdf_task(self, pdf_path: str):
    self.update_state(state='PROGRESS', meta={'current_step': 'Starting PDF processing', 'pdf_path': pdf_path})

    try:
        # 1) Convert PDF pages to images
        self.update_state(state='PROGRESS', meta={'current_step': 'Converting PDF to images'})
        page_images = pdf_processor.pdf_to_images(pdf_path)

        # Structure output chuẩn cho ExcelExporter
        extracted_data_list = {"position": [], "transaction": {"trade": [], "fx_tf": [], "other": []}}

        # Metadata fallback scan across pages (không chỉ first page)
        metadata_set = False
        client_name = ""
        portfolio_no = ""
        valuation_date = ""

        # Duyệt từng trang
        for i, image in enumerate(page_images):
            self.update_state(
                state='PROGRESS',
                meta={'current_step': f'Processing page {i+1}/{len(page_images)}'}
            )

            # 2) OCR ONCE per page
            ocr_result = pdf_processor.perform_ocr(image)

            # Lấy rec_texts an toàn (vì format OCR có thể khác)
            rec_texts = []
            if ocr_result and ocr_result[0] and isinstance(ocr_result[0], dict):
                rec_texts = ocr_result[0].get("rec_texts", []) or []

            # 3) Set metadata khi tìm thấy trang có đủ marker
            if (not metadata_set) and _has_portfolio_and_statement(rec_texts):
                try:
                    # client name: dùng token list theo rule (utils.get_client_name_from_text)
                    client_name = get_client_name_from_text(rec_texts)

                    # portfolio/date: parse từ full_text
                    full_text = " ".join(rec_texts) if rec_texts else ""
                    portfolio_no = get_portfolio_no_from_text(full_text)
                    valuation_date = get_valuation_date_from_text(full_text)

                    # bơm metadata vào processors
                    pdf_processor.transaction_processor.client_name = client_name
                    pdf_processor.postion_processor.portfolio_no = portfolio_no
                    pdf_processor.postion_processor.valuation_date = valuation_date

                    metadata_set = True
                except Exception:
                    # không block pipeline nếu parse metadata lỗi
                    pass

            # 4) Classify page type (NO extra OCR)
            page_type = pdf_processor.classify_page(ocr_result)

            # 5) Extract info theo page type
            extracted_info = pdf_processor.extract_info(image, ocr_result, page_type)

            if not extracted_info:
                continue

            if page_type == "position":
                # position processor trả list[dict]
                if isinstance(extracted_info, list):
                    extracted_data_list["position"].extend(extracted_info)
            elif page_type == "transaction":
                # transaction processor trả dict có keys trade_info/fx_tf_info/other_info
                if isinstance(extracted_info, dict):
                    extracted_data_list["transaction"]["trade"].extend(extracted_info.get("trade_info", []))
                    extracted_data_list["transaction"]["fx_tf"].extend(extracted_info.get("fx_tf_info", []))
                    extracted_data_list["transaction"]["other"].extend(extracted_info.get("other_info", []))
            else:
                # other pages -> ignore
                continue

        # Nếu không tìm thấy metadata ở trang nào -> set default an toàn
        if not metadata_set:
            try:
                pdf_processor.transaction_processor.client_name = ""
                pdf_processor.postion_processor.portfolio_no = ""
                pdf_processor.postion_processor.valuation_date = ""
            except Exception:
                pass

        # 6) Export data to Excel (ONLY 4 files)
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
