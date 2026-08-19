# dealflow web app + mock agent (single image; role chosen by compose command).
# KakaoDesktopSender (pywinauto) is NOT installed here — Windows-native only.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY . .

# Entrypoint runs migrations + idempotent seed, then execs the given command.
RUN chmod +x scripts/entrypoint.sh

ENV DEALFLOW_DATA_DIR=/app/data \
    DATABASE_URL=sqlite:////app/data/dealflow.db

EXPOSE 8000
ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
