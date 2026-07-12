FROM python:3.11-slim

WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml setup.py ./
COPY app ./app

RUN pip install --upgrade pip setuptools wheel \
    && pip install .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
