FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install OCR executable and Arabic/English language data at image-build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       tesseract-ocr-ara \
       tesseract-ocr-eng \
    && command -v tesseract \
    && tesseract --list-langs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# Keep database migration and app startup in one command for compatibility
# with the current Render service configuration.
CMD ["sh", "-c", "flask db upgrade && exec gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-10000} app:app"]
