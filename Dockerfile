FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000 8501

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
