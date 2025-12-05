# Broker Document Extractor

This project implements a FastAPI application for extracting information from multi-page broker PDF documents. It leverages Celery and Redis for asynchronous processing, PaddleOCR for text recognition, and exports the extracted data to an Excel file.

## Architecture

The application consists of the following main components:

1.  **FastAPI Application:**
    *   Provides a RESTful API for users to upload PDF files.
    *   Initiates asynchronous processing tasks via Celery.
    *   Offers endpoints to query the status of processing tasks and retrieve the final Excel output.

2.  **Celery Worker:**
    *   A background worker that consumes tasks from the Redis message broker.
    *   Responsible for the core logic:
        *   **PDF Parsing:** Converts PDF pages into images for OCR.
        *   **Page Classification:** Determines if a page is a 'position' or 'transaction' page.
        *   **OCR (PaddleOCR):** Extracts text and structured data from page images.
        *   **Data Extraction:** Parses the OCR output to identify relevant information.
        *   **Excel Generation:** Compiles the extracted data into a structured Excel spreadsheet.

3.  **Redis:**
    *   Serves as the message broker for Celery, facilitating communication between the FastAPI app and the Celery worker.
    *   Acts as the result backend for Celery, storing the status and results of executed tasks.

4.  **PaddleOCR:**
    *   An open-source OCR library used for robust text recognition on the image representations of PDF pages.

## Project Structure

```
broker_extractor/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI application entry point
│   ├── tasks.py            # Celery tasks definition
│   ├── services/           # Business logic and helper functions
│   │   ├── __init__.py
│   │   ├── pdf_processor.py # Handles PDF to image conversion, page classification, OCR
│   │   └── excel_exporter.py # Handles data to Excel conversion
│   └── models/             # Data models (e.g., Pydantic models for API, data structures)
│       └── __init__.py
├── config.py               # Configuration settings for FastAPI, Celery, Redis
├── Dockerfile              # Dockerfile for the FastAPI application and Celery worker
├── docker-compose.yml      # Docker Compose for orchestrating services (FastAPI, Celery, Redis)
├── requirements.txt        # Python dependencies
└── README.md               # Project overview and documentation
```

## Setup and Deployment

Detailed instructions for setting up the environment, running the application locally, and deploying with Docker will be provided in subsequent sections.
