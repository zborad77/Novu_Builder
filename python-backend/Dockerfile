FROM python:3.12-slim

WORKDIR /app

# Systémové závislosti pro psycopg (binary) a Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Storage adresář pro fotky a exporty
RUN mkdir -p /data/storage

EXPOSE 8000

# Spustí migrace a pak server
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
