#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [ ! -f .pid ]; then
  echo "[stop] no .pid file; nothing to stop"
  exit 0
fi

PID="$(cat .pid)"
if ! kill -0 "$PID" 2>/dev/null; then
  echo "[stop] pid $PID not alive; clearing .pid"
  rm -f .pid
  exit 0
fi

echo "[stop] sending SIGTERM to $PID"
kill -TERM "$PID"

for _ in $(seq 1 10); do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f .pid
    echo "[stop] stopped"
    exit 0
  fi
  sleep 1
done

echo "[stop] SIGTERM ignored, sending SIGKILL"
kill -9 "$PID" 2>/dev/null || true
rm -f .pid