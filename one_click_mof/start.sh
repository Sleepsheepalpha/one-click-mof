#!/usr/bin/env bash
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/.."
PORT="${1:-8765}"
URL="http://127.0.0.1:${PORT}"
if curl -sS "$URL/api/settings" >/dev/null 2>&1; then
  echo "One-Click MOF 已经在运行：$URL"
  xdg-open "$URL" >/dev/null 2>&1 || true
  exit 0
fi
( sleep 1; xdg-open "$URL" >/dev/null 2>&1 || true ) &
echo "One-Click MOF：$URL"
exec python3 "$HERE/app.py" --port "$PORT"
