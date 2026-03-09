# PropEdge v2 - Python Backend Docker Image
# Runs the FastAPI trading system backend headless on EC2
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROPEDGE_ENV=production \
    PROPEDGE_DATA_DIR=/data \
    PROPEDGE_CONFIG=/app/configs/default.yaml

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt || true

# Remove pandas-ta if it fails (we have custom indicators)
RUN pip install --no-cache-dir pandas-ta 2>/dev/null || echo "pandas-ta not available, using custom indicators"

# Copy the application code
COPY core/ ./core/
COPY data_engine/ ./data_engine/
COPY feature_engine/ ./feature_engine/
COPY agents/ ./agents/
COPY backtester/ ./backtester/
COPY allocator/ ./allocator/
COPY risk_manager/ ./risk_manager/
COPY execution/ ./execution/
COPY evolution/ ./evolution/
COPY api/ ./api/
COPY configs/ ./configs/
COPY scripts/ ./scripts/

# Create data directories
RUN mkdir -p /data/duckdb /data/sqlite /data/models /data/logs

# Make entrypoint executable
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Expose the API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Use entrypoint script (auto-generates sample data on first run)
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
