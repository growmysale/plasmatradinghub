#!/bin/bash
# Start PropEdge Frontend dev server
cd "$(dirname "$0")/../packages/frontend"
echo "Starting PropEdge Frontend on http://localhost:3000"
npx vite --port 3000
