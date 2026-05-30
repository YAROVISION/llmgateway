FROM python:3.11-slim

# Системні залежності
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Спочатку лише requirements — щоб Docker кешував шар з залежностями
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь код
COPY . .

# Директорія для runtime-файлів (failures.json тощо)
RUN mkdir -p scratch

# Не запускати як root
RUN useradd -m -u 1000 gateway
RUN chown -R gateway:gateway /app
USER gateway

EXPOSE 8000

# Healthcheck для Docker / Hostinger
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
