FROM pytorch/pytorch:2.8.0-cuda12.6-cudnn9-devel

# System libs needed by OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    poppler-utils \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
 && rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
# Install Python dependencies
COPY requirements.txt .
RUN pip install -U pip
RUN pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
RUN pip install --no-cache-dir -r requirements.txt

# Install PaddleOCR models (optional, can be downloaded at runtime)
# This step can be time-consuming, consider doing it at runtime or pre-baking into a custom image
# RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(lang=\'en\')"

COPY . .

# Expose the port FastAPI runs on
EXPOSE 8000

# Command to run the FastAPI application (default)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

