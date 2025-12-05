import os

class Settings:
    PROJECT_NAME: str = "Broker Extractor"
    PROJECT_VERSION: str = "1.0.0"

    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

settings = Settings()

