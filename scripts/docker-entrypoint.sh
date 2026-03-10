#!/bin/bash
# PropEdge v2 Docker Entrypoint
set -e

echo "=== PropEdge v2 Starting ==="
echo "Environment: ${PROPEDGE_ENV:-development}"
echo "Data dir: ${PROPEDGE_DATA_DIR:-/data}"
echo "Config: ${PROPEDGE_CONFIG:-/app/configs/default.yaml}"

# Create data directories if needed
mkdir -p "${PROPEDGE_DATA_DIR:-/data}"/{duckdb,sqlite,models,logs}

echo "=== Starting API Server ==="
echo "Sample data will be auto-generated on first request if DB is empty."
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
