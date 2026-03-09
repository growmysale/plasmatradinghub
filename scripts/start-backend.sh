#!/bin/bash
# Start PropEdge Backend API
cd "$(dirname "$0")/../packages/backend"
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate 2>/dev/null
echo "Starting PropEdge Backend on http://localhost:8080"
uvicorn main:app --host 0.0.0.0 --port 8080 --reload --app-dir .
