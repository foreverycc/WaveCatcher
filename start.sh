#!/usr/bin/env bash
# Start WaveCatcher: the FastAPI backend (port 8000) and the web frontend (port 5173).
#   ./start.sh        production frontend (builds, then serves; fast)
#   ./start.sh dev    development frontend (reloads on every code change; slower)
# Ctrl+C stops both. If either one exits, the other is stopped too.
# Python: the `python` on PATH (set PYTHON=/path/to/python to use another one).

set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-prod}"
PYTHON="${PYTHON:-python}"

case "$MODE" in
  prod) FRONTEND_CMD="npm run serve" ;;
  dev) FRONTEND_CMD="npm run dev" ;;
  *) echo "Usage: ./start.sh [dev]"; exit 1 ;;
esac

for port in 8000 5173; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use - is WaveCatcher already running?"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN | sed 's/^/  /'
    exit 1
  fi
done

# stop a process and everything it started
kill_tree() {
  local pid=$1 child
  for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$pid" 2>/dev/null
}

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping WaveCatcher..."
  [ -n "$BACKEND_PID" ] && kill_tree "$BACKEND_PID"
  [ -n "$FRONTEND_PID" ] && kill_tree "$FRONTEND_PID"
  wait 2>/dev/null
  echo "Stopped."
  exit 0
}
trap cleanup INT TERM EXIT

echo "Starting backend:  $PYTHON -m app.main  (http://localhost:8000)"
(cd "$ROOT/backend" && PYTHONUNBUFFERED=1 exec "$PYTHON" -m app.main) \
  > >(sed -l 's/^/[backend]  /') 2>&1 &
BACKEND_PID=$!

echo "Starting frontend: $FRONTEND_CMD  (http://localhost:5173)"
(cd "$ROOT/frontend" && exec $FRONTEND_CMD) \
  > >(sed -l 's/^/[frontend] /') 2>&1 &
FRONTEND_PID=$!

# keep running until one of them exits
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
kill -0 "$BACKEND_PID" 2>/dev/null || echo "Backend exited."
kill -0 "$FRONTEND_PID" 2>/dev/null || echo "Frontend exited."
