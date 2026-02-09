from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from celery.result import AsyncResult
import os
import shutil
import tempfile
import zipfile
from starlette.background import BackgroundTask

from config import settings
from app.tasks import process_pdf_task

OUTPUT_DIR = "./outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title=settings.PROJECT_NAME, version=settings.PROJECT_VERSION)

UPLOAD_DIR = "./uploaded_pdfs"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


@app.post("/soa/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_location = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    task = process_pdf_task.delay(file_location)
    return JSONResponse({"message": "PDF processing started", "task_id": task.id})


@app.get("/task-status/{task_id}/")
async def get_task_status(task_id: str):
    task = AsyncResult(task_id)
    if task.state == "PENDING":
        return JSONResponse({"status": "Pending"})
    elif task.state == "PROGRESS":
        return JSONResponse({"status": "Processing", "info": task.info})
    elif task.state == "SUCCESS":
        return JSONResponse({"status": "Success", "result": task.result})
    elif task.state == "FAILURE":
        return JSONResponse({"status": "Failed", "error": str(task.result)})
    else:
        return JSONResponse({"status": task.state})


@app.get("/download-excel/{task_id}/")
async def list_excel_files(task_id: str):
    target_dir = os.path.join(OUTPUT_DIR, task_id)
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="Result folder not found.")

    # lấy file .xlsx (không recursive)
    excel_files = [
        f
        for f in os.listdir(target_dir)
        if f.lower().endswith(".xlsx") and os.path.isfile(os.path.join(target_dir, f))
    ]
    if not excel_files:
        raise HTTPException(status_code=404, detail="No Excel files found for this task.")

    files_payload = [
        {"filename": fname, "url": f"/download-excel-file/{task_id}/{fname}"}
        for fname in excel_files
    ]

    return JSONResponse(
        {
            "folder": target_dir,
            "file_count": len(excel_files),
            "files": files_payload,
            "download_all_url": f"/download-all-excel/{task_id}/",
        }
    )


@app.get("/download-excel-file/{task_id}/{filename}")
async def download_single_excel(task_id: str, filename: str):
    # chặn path traversal / file ẩn
    if os.path.sep in filename or filename.startswith(".") or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    folder_path = os.path.join(OUTPUT_DIR, task_id)
    file_path = os.path.join(folder_path, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@app.get("/download-all-excel/{task_id}/")
async def download_all_excel(task_id: str):
    target_dir = os.path.join(OUTPUT_DIR, task_id)
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="Result folder not found.")

    excel_files = [
        f
        for f in os.listdir(target_dir)
        if f.lower().endswith(".xlsx") and os.path.isfile(os.path.join(target_dir, f))
    ]
    if not excel_files:
        raise HTTPException(status_code=404, detail="No Excel files found for this task.")

    # tạo file zip tạm
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".zip") as tmp_zip:
        zip_path = tmp_zip.name

    # ghi zip (mở lại theo path để chắc chắn file được đóng đúng cách)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for fname in excel_files:
            file_path = os.path.join(target_dir, fname)
            zipf.write(file_path, arcname=fname)

    def cleanup(path: str):
        if os.path.exists(path):
            os.unlink(path)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{task_id}_excel_files.zip",
        background=BackgroundTask(cleanup, zip_path),
    )
