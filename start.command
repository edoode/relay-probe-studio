#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

BIND_HOST="${BIND_HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
URL="http://${BIND_HOST}:${PORT}"

pause_on_exit() {
  if [[ -t 0 ]]; then
    echo
    read -r "?Press Enter to close..."
  fi
}

is_relay_ui_running() {
  local body
  body="$(curl -fsS "${URL}/" 2>/dev/null || true)"
  [[ "$body" == *"Relay Probe Studio"* ]]
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3 first."
  pause_on_exit
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl was not found. Install curl first."
  pause_on_exit
  exit 1
fi

if is_relay_ui_running; then
  echo "Relay Probe UI is already running at ${URL}"
  if [[ "$OPEN_BROWSER" == "1" ]]; then
    open "${URL}" >/dev/null 2>&1 || true
  fi
  exit 0
fi

echo "Starting Relay Probe UI at ${URL}"
python3 probe_web.py --host "$BIND_HOST" --port "$PORT" &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

READY=0
for _ in {1..40}; do
  if is_relay_ui_running; then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "$READY" -ne 1 ]]; then
  echo "The UI did not become ready in time."
  echo "Check the server logs above for details."
  wait "$SERVER_PID"
  pause_on_exit
  exit 1
fi

if [[ "$OPEN_BROWSER" == "1" ]]; then
  open "${URL}" >/dev/null 2>&1 || true
fi

echo
echo "Relay Probe UI is running."
echo "Open: ${URL}"
echo "Keep this Terminal window open while using the app."
echo "Press Ctrl+C here to stop the server."
echo

wait "$SERVER_PID"
