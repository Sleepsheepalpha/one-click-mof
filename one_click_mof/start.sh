#!/usr/bin/env bash
# One-Click MOF desktop/terminal launcher.
# - starts the local server from any working directory
# - reuses it if it is already running
# - opens the browser automatically
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8765}"
URL="http://127.0.0.1:${PORT}"
LOG_DIR="$HERE/data"
LOG="$LOG_DIR/launcher.log"
PY="$ROOT/.venv_mace/bin/python"

mkdir -p "$LOG_DIR"

open_url() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
  elif command -v gio >/dev/null 2>&1; then
    gio open "$URL" >/dev/null 2>&1 &
  fi
}

show_error() {
  if command -v zenity >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    zenity --error --title="One-Click MOF" --text="$1" >/dev/null 2>&1 || true
  fi
}

if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ]; then
  show_error "找不到 Python。请先按 README 创建 .venv_mace 环境。"
  exit 1
fi

# Already running: just open the page.
if curl --max-time 1 -fsS "$URL/api/settings" >/dev/null 2>&1; then
  open_url
  exit 0
fi

# Start the server in the background so this launcher can report failures.
"$PY" "$HERE/app.py" --port "$PORT" >>"$LOG" 2>&1 &
PID=$!

cleanup() {
  kill "$PID" 2>/dev/null || true
}
trap cleanup INT TERM

(
  for _ in $(seq 1 50); do
    if curl --max-time 1 -fsS "$URL/api/settings" >/dev/null 2>&1; then
      open_url
      exit 0
    fi
    sleep 0.3
  done
  show_error "One-Click MOF 启动超时。请查看：\n$LOG"
) &
WAITER=$!

wait "$PID"
RC=$?
kill "$WAITER" 2>/dev/null || true
if [ "$RC" -ne 0 ]; then
  show_error "One-Click MOF 启动失败。请查看：\n$LOG"
fi
exit "$RC"
