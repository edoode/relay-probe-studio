#!/bin/zsh

set -euo pipefail

CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD_DIR="$CONTENTS_DIR/Resources/app"

BIND_HOST="${BIND_HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
URL="http://${BIND_HOST}:${PORT}"
LOG_FILE="${TMPDIR:-/tmp}/relay-probe-ui.log"

show_alert() {
  local title="$1"
  local message="$2"
  /usr/bin/osascript -e "display alert \"${title}\" message \"${message}\" as critical" >/dev/null 2>&1 || true
}

find_python() {
  local candidate
  local -a candidates=(
    "${PYTHON_BIN:-}"
    "/usr/bin/python3"
    "/opt/miniconda3/bin/python3"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  return 1
}

is_running() {
  local body
  body="$(/usr/bin/curl -fsS "${URL}/" 2>/dev/null || true)"
  [[ "$body" == *"Relay Probe Studio"* ]]
}

open_browser() {
  if [[ "$OPEN_BROWSER" == "1" ]]; then
    /usr/bin/open "${URL}" >/dev/null 2>&1 || true
  fi
}

spawn_server() {
  local python_bin="$1"
  APP_PYTHON="$python_bin" \
  APP_PAYLOAD_DIR="$PAYLOAD_DIR" \
  APP_LOG_FILE="$LOG_FILE" \
  APP_HOST="$BIND_HOST" \
  APP_PORT="$PORT" \
  "$python_bin" - <<'PY'
import os
import subprocess

python_bin = os.environ["APP_PYTHON"]
payload_dir = os.environ["APP_PAYLOAD_DIR"]
log_file = os.environ["APP_LOG_FILE"]
host = os.environ["APP_HOST"]
port = os.environ["APP_PORT"]

with open(log_file, "ab", buffering=0) as handle:
    subprocess.Popen(
        [python_bin, os.path.join(payload_dir, "probe_web.py"), "--host", host, "--port", port],
        cwd=payload_dir,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
PY
}

main() {
  if [[ ! -f "$PAYLOAD_DIR/probe_web.py" ]]; then
    show_alert "中转稳定性检测" "应用资源不完整，缺少 probe_web.py。"
    exit 1
  fi

  if is_running; then
    open_browser
    exit 0
  fi

  local python_bin
  python_bin="$(find_python || true)"
  if [[ -z "$python_bin" ]]; then
    show_alert "中转稳定性检测" "没有找到 Python 3，无法启动本地服务。"
    exit 1
  fi

  spawn_server "$python_bin"

  for _ in {1..40}; do
    if is_running; then
      open_browser
      exit 0
    fi
    sleep 0.5
  done

  show_alert "中转稳定性检测" "应用已尝试启动，但本地服务未能及时就绪。日志位置：$LOG_FILE"
  exit 1
}

main "$@"
