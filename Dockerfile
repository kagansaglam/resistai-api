FROM python:3.11-slim

# fpocket'i kaynaktan derle. Modern GCC eski C kodundaki pointer tip
# uyumsuzluklarini hata sayiyor; -Wno-* flagleriyle uyariya dusurup derliyoruz.
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libnetcdf-dev \
        ca-certificates && \
    git clone https://github.com/Discngine/fpocket.git /tmp/fpocket && \
    cd /tmp/fpocket && \
    make CFLAGS="-O2 -std=gnu89 -Wno-incompatible-pointer-types -Wno-implicit-function-declaration -Wno-int-conversion -fcommon" && \
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
