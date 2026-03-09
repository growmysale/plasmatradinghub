#!/bin/bash
# PropEdge v2 Docker Entrypoint
# Initializes data on first run, then starts the API server

set -e

echo "=== PropEdge v2 Starting ==="
echo "Environment: ${PROPEDGE_ENV:-development}"
echo "Data dir: ${PROPEDGE_DATA_DIR:-/data}"
echo "Config: ${PROPEDGE_CONFIG:-/app/configs/default.yaml}"

# Create data directories if needed
mkdir -p "${PROPEDGE_DATA_DIR:-/data}"/{duckdb,sqlite,models,logs}

# Generate sample data if database is empty (first run)
if [ ! -f "${PROPEDGE_DATA_DIR:-/data}/sqlite/candles.db" ] && \
   [ ! -f "${PROPEDGE_DATA_DIR:-/data}/propedge.db" ]; then
    echo "=== First run: generating sample data ==="
    python /app/scripts/generate_sample_data.py 90 || echo "Sample data generation skipped"
fi

echo "=== Starting API Server ==="
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
