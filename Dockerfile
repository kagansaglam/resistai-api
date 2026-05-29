# fpocket'in resmi, onceden derlenmis imaji - derleme yok
FROM fpocket/fpocket

# Python ve pip kur (bu image Debian/Ubuntu tabanli)
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT
