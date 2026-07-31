#!/usr/bin/env bash

set -euo pipefail

PORT="${1:-8001}"
HOST="127.0.0.1"

cd "$(dirname "$0")/.."

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "Usage: $0 [port]"
  exit 2
fi

PIDS=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

if [[ -n "$PIDS" ]]; then
  echo "Stopping existing processes on port $PORT..."
  echo "$PIDS" | xargs kill -TERM
  sleep 2

  REMAINING=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

  if [[ -n "$REMAINING" ]]; then
    echo "Force-stopping remaining processes..."
    echo "$REMAINING" | xargs kill -KILL
  fi
else
  echo "Port $PORT is already available."
fi

# Use the repository virtual environment when available.
if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Error: Python 3 was not found."
  exit 1
fi

if ! "$PYTHON" -c "import uvicorn" >/dev/null 2>&1; then
  echo "Error: uvicorn is not installed for $PYTHON"
  echo "Install dependencies first."
  exit 1
fi

echo "Starting EchoSense at http://$HOST:$PORT"
exec "$PYTHON" -m uvicorn echosense.product_app:app \
  --app-dir src \
  --host "$HOST" \
  --port "$PORT"
