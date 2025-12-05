# Broker Extraction API

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green.svg)](https://fastapi.tiangolo.com)

A production-ready API service for automated extraction and processing of broker statements and financial documents. Built with FastAPI and Celery for asynchronous processing, this service leverages computer vision and OCR technologies to extract structured data from PDF documents.

## 🌟 Features

- **Asynchronous PDF Processing**: Handle large documents without blocking using Celery workers
- **Intelligent Page Classification**: Automatically categorize pages as position or transaction types
- **Advanced OCR**: Powered by PaddleOCR for accurate text extraction
- **Document Understanding**: YOLO-based table detection and structure recognition
- **Excel Export**: Structured data output in Excel format for easy analysis
- **GPU Acceleration**: CUDA support for fast processing
- **RESTful API**: Clean, well-documented endpoints for easy integration
- **Docker Support**: Containerized deployment with Docker Compose
- **Production Ready**: Redis-backed task queue with result tracking

## 📋 Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## 🏗 Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Client    │─────▶│  FastAPI App │─────▶│    Redis    │
└─────────────┘      └──────────────┘      └─────────────┘
                            │                      │
                            │                      │
                            ▼                      ▼
                     ┌──────────────┐      ┌─────────────┐
                     │ Celery Worker│◀─────│ Task Queue  │
                     └──────────────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ PDF Processor│
                     │  - OCR       │
                     │  - YOLO      │
                     │  - Extraction│
                     └──────────────┘
```

### Components

- **FastAPI App**: REST API server handling requests and responses
- **Celery Worker**: Background task processor for PDF analysis
- **Redis**: Message broker and result backend
- **PDF Processor**: Core extraction engine with OCR and computer vision
- **Excel Exporter**: Structured data formatting and export

## 🔧 Prerequisites

- Python 3.9+
- Docker & Docker Compose (recommended)
- NVIDIA GPU with CUDA 12.6+ (for GPU acceleration)
- poppler-utils (for PDF processing)

## 📦 Installation

### Using Docker Compose (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd broker-extraction-api
   ```

2. **Build and start services**
   ```bash
   docker-compose up -d --build
   ```

3. **Verify services are running**
   ```bash
   docker-compose ps
   ```

The API will be available at `http://localhost:8022`

### Manual Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd broker-extraction-api
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   # Install PaddlePaddle GPU version
   pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
   
   # Install other requirements
   pip install -r requirements.txt
   ```

4. **Install system dependencies**
   ```bash
   sudo apt-get update
   sudo apt-get install -y libgl1 poppler-utils libglib2.0-0 libsm6 libxrender1 libxext6
   ```

5. **Start Redis**
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   ```

6. **Start the application**
   ```bash
   # Terminal 1: Start FastAPI
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   
   # Terminal 2: Start Celery worker
   celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Project Settings
PROJECT_NAME=Broker Extractor
PROJECT_VERSION=1.0.0

# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# GPU Configuration (for Docker)
NVIDIA_VISIBLE_DEVICES=0
```

### Docker Configuration

Modify `docker-compose.yml` to adjust:
- Port mappings (default: `8022:8000`)
- GPU device allocation (`NVIDIA_VISIBLE_DEVICES`)
- Volume mounts for persistent storage
- Redis port (default: `6392:6379`)

## 🚀 Usage

### Basic Workflow

1. **Upload a PDF document**
2. **Receive a task ID**
3. **Poll task status**
4. **Download results when complete**

### Quick Start Example

```python
import requests

# 1. Upload PDF
with open('broker_statement.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8022/soa/upload-pdf/',
        files={'file': f}
    )
task_id = response.json()['task_id']

# 2. Check status
status_response = requests.get(
    f'http://localhost:8022/task-status/{task_id}/'
)
print(status_response.json())

# 3. Download results
results = requests.get(
    f'http://localhost:8022/download-excel/{task_id}/'
)
print(results.json())
```

### Using cURL

```bash
# Upload PDF
curl -X POST "http://localhost:8022/soa/upload-pdf/" \
  -F "file=@broker_statement.pdf"

# Check task status
curl "http://localhost:8022/task-status/<task_id>/"

# List available Excel files
curl "http://localhost:8022/download-excel/<task_id>/"

# Download specific file
curl -O "http://localhost:8022/download-excel-file/<task_id>/<filename.xlsx>"

# Download all files as ZIP
curl -O "http://localhost:8022/download-all-excel/<task_id>/"
```

## 📡 API Endpoints

### POST `/soa/upload-pdf/`

Upload a PDF file for asynchronous processing.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: PDF file

**Response:**
```json
{
  "message": "PDF processing started",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### GET `/task-status/{task_id}/`

Check the processing status of a submitted task.

**Response:**
```json
{
  "status": "Success",
  "result": {
    "message": "PDF processed successfully",
    "output_folder": "outputs/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**Status Values:**
- `Pending`: Task queued but not started
- `Processing`: Currently being processed
- `Success`: Completed successfully
- `Failed`: Processing failed (includes error details)

### GET `/download-excel/{task_id}/`

List all Excel files generated for a task.

**Response:**
```json
{
  "folder": "outputs/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "file_count": 2,
  "files": [
    {
      "filename": "position.xlsx",
      "url": "/download-excel-file/<task_id>/position.xlsx"
    },
    {
      "filename": "transactions.xlsx",
      "url": "/download-excel-file/<task_id>/transactions.xlsx"
    }
  ],
  "download_all_url": "/download-all-excel/<task_id>/"
}
```

### GET `/download-excel-file/{task_id}/{filename}`

Download a specific Excel file.

**Response:** Excel file (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

### GET `/download-all-excel/{task_id}/`

Download all Excel files for a task as a ZIP archive.

**Response:** ZIP file (application/zip)

## 🛠 Development

### Project Structure

```
broker-extraction-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── tasks.py             # Celery tasks
│   ├── utils.py             # Utility functions
│   ├── models/              # Data models
│   ├── services/            # Business logic
│   │   ├── pdf_processor.py      # PDF processing
│   │   ├── excel_exporter.py     # Excel generation
│   │   └── ...
│   └── weights/             # Model weights
├── config.py                # Configuration settings
├── requirements.txt         # Python dependencies
├── Dockerfile              # Container definition
├── docker-compose.yml      # Multi-container setup
├── uploaded_pdfs/          # Temporary PDF storage
├── outputs/                # Processed results
├── cache/                  # Model cache
└── README.md
```

### Running Tests

```bash
# Run unit tests
pytest tests/

# Run with coverage
pytest --cov=app tests/
```

### Code Quality

```bash
# Format code
black app/

# Lint code
flake8 app/

# Type checking
mypy app/
```

### Adding New Features

1. Create a new branch: `git checkout -b feature/your-feature`
2. Implement your changes
3. Add tests for new functionality
4. Update documentation
5. Submit a pull request

## 🚢 Deployment

### Production Checklist

- [ ] Set strong Redis password
- [ ] Configure proper CORS settings
- [ ] Set up SSL/TLS certificates
- [ ] Configure logging and monitoring
- [ ] Set up automated backups
- [ ] Configure resource limits
- [ ] Enable error tracking (e.g., Sentry)
- [ ] Set up health check endpoints
- [ ] Configure rate limiting
- [ ] Review security settings

### Docker Deployment

```bash
# Build production image
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f

# Scale workers
docker-compose up -d --scale celery_worker=3
```

### Environment-Specific Configuration

For production, create `docker-compose.prod.yml` with:
- Production-grade Redis configuration
- Proper volume mounts
- Resource limits
- Restart policies
- Logging drivers

## 🔍 Troubleshooting

### Common Issues

**1. Redis Connection Failed**
```bash
# Check Redis is running
docker-compose ps redis

# Check Redis logs
docker-compose logs redis
```

**2. GPU Not Detected**
```bash
# Verify NVIDIA runtime
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi

# Check GPU allocation in docker-compose.yml
```

**3. Task Stays in Pending State**
```bash
# Check Celery worker is running
docker-compose ps celery_worker

# View worker logs
docker-compose logs celery_worker
```

**4. OCR Errors**
```bash
# Clear model cache
rm -rf cache/.paddlex/

# Restart services
docker-compose restart
```

### Performance Optimization

- Increase Celery worker pool size for parallel processing
- Adjust CUDA device allocation based on available GPUs
- Configure Redis memory limits for large workloads
- Use SSD storage for faster I/O operations

### Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f fastapi_app
docker-compose logs -f celery_worker

# Save logs to file
docker-compose logs > logs.txt
```

## 📊 Monitoring

### Health Check

```bash
# Check API health
curl http://localhost:8022/

# Check Celery worker
celery -A app.tasks.celery_app inspect active
```

### Metrics

Monitor these key metrics:
- Task processing time
- Queue length
- Success/failure rates
- Memory usage
- GPU utilization

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

Please ensure your code follows the existing style and includes appropriate tests.

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [Celery](https://docs.celeryproject.org/) - Distributed task queue
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - OCR toolkit
- [Ultralytics](https://github.com/ultralytics/ultralytics) - YOLO models
- [Redis](https://redis.io/) - Message broker

## 📞 Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check existing documentation
- Review closed issues for solutions

---

**Made with ❤️ by AIRC-Lab**