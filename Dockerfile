FROM python:3.11-slim

# fpocket + derleme/runtime bağımlılıkları (libnetcdf fpocket 3.x için gerekli)
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        fpocket \
        libnetcdf19 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Önce requirements (Docker layer cache için)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu
COPY . .

# Render $PORT enjekte eder; default 8000
ENV PORT=8000
EXPOSE 8000

# Mevcut start komutuyla birebir aynı
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
