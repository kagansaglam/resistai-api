# micromamba (conda) tabanli - fpocket'i conda-forge'dan onceden derlenmis kurar.
# Derleme yok, GCC/netcdf/flag derdi yok.
FROM mambaorg/micromamba:1.5.8

USER root

# Sistem CA sertifikalari (https istekleri icin)
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* || true

# fpocket + python'i conda-forge'dan kur
RUN micromamba install -y -n base -c conda-forge \
        python=3.11 \
        fpocket \
        pip && \
    micromamba clean --all --yes

# micromamba ortamini aktif et
ARG MAMBA_DOCKERFILE_ACTIVATE=1
ENV PATH=/opt/conda/bin:$PATH

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
