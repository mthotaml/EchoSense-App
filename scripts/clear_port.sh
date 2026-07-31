#!/usr/bin/env bash

set -euo pipefail

PORT="${1:-8001}"

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "Usage: $0 [port]"
  exit 2
fi

PIDS=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

if [[ -z "$PIDS" ]]; then
  echo "Port $PORT is already available."
  exit 0
fi

echo "Processes listening on port $PORT:"
lsof -nP -iTCP:"$PORT" -sTCP:LISTEN

echo "Stopping processes..."
echo "$PIDS" | xargs kill -TERM
sleep 2

REMAINING=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

if [[ -n "$REMAINING" ]]; then
  echo "Force-stopping remaining processes..."
  echo "$REMAINING" | xargs kill -KILL
fi

echo "Port $PORT is now available."
