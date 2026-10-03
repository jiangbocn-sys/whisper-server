#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

mkdir -p logs

if [ ! -d .venv ]; then
  echo "[start] creating venv..."
  python3 -m venv .venv
fi

# 任何依赖变动都顺手装一次
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

if [ -f .pid ] && kill -0 "$(cat .pid)" 2>/dev/null; then
  echo "[start] already running pid=$(cat .pid)"
  exit 0
fi

echo "[start] launching in background, logs -> logs/server.log"
nohup .venv/bin/python server.py > logs/server.log 2>&1 &
echo $! > .pid
echo "[start] pid=$(cat .pid)"