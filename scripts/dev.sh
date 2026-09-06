#!/usr/bin/env bash
# Run the API (port 8000) and the Vite dev server (port 5173, proxies /api) together.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && python -m uvicorn app.main:app --reload --port 8000) &
API=$!
trap 'kill $API' EXIT
cd frontend && npm run dev
