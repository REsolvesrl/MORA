# Immagine per il deploy su Render (o qualsiasi host che supporti Docker).
#
# NOTA: Streamlit Community Cloud NON usa questo file: là valgono
# requirements.txt + packages.txt. Questo serve agli host "veri" (Render,
# VPS, ecc.) dove i pacchetti di sistema vanno installati esplicitamente.

FROM python:3.12-slim

# Pacchetti di sistema richiesti dall'OCR: Tesseract (con lingua italiana)
# e Poppler (rendering delle pagine PDF in immagine).
# Sono gli stessi elencati in packages.txt per Streamlit Cloud.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ita \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Le dipendenze prima del codice: così Docker riusa la cache quando
# cambiano solo i sorgenti.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Render inietta $PORT a runtime; in locale si usa 8501.
EXPOSE 8501
CMD streamlit run streamlit_app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0
