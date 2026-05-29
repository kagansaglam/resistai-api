FROM python:3.11-slim

# fpocket'i kaynaktan derlemek icin gerekli araclar + runtime kutuphaneleri
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libnetcdf-dev \
        ca-certificates && \
    git clone https://github.com/Discngine/fpocket.git /tmp/fpocket && \
    cd /tmp/fpocket && \
    make && \
    make install && \
    cd / && \
    rm -rf /tmp/fpocket && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
