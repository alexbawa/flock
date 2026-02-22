#!/usr/bin/env bash
# Start Flask and Celery together for local development.
# Run from the backend/ directory:  bash run_dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env from backend/ if present
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Activate virtualenv if present
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/venv/bin/activate"
fi

cleanup() {
    echo ""
    echo "Stopping Flask and Celery…"
    kill "$FLASK_PID" "$CELERY_PID" 2>/dev/null || true
    wait "$FLASK_PID" "$CELERY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting Flask…"
FLASK_APP=app FLASK_DEBUG=1 python -m flask run &
FLASK_PID=$!

echo "Starting Celery…"
celery -A app worker --loglevel=info &
CELERY_PID=$!

echo ""
echo "Flask  PID: $FLASK_PID  (http://localhost:5000)"
echo "Celery PID: $CELERY_PID"
echo "Press Ctrl+C to stop both."
echo ""

wait
