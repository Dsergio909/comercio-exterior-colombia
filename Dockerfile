# Imagen del pipeline (Python + DuckDB). La usa docker-compose.yml.
FROM python:3.12-slim
WORKDIR /app
COPY requirements-pipeline.txt .
RUN pip install --no-cache-dir -r requirements-pipeline.txt
COPY scripts ./scripts
COPY sql ./sql
EXPOSE 5688
CMD ["python", "scripts/servidor.py", "--host", "0.0.0.0"]
