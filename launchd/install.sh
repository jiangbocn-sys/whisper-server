#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$HERE/com.bobo.whisper-server.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.bobo.whisper-server.plist"

if [ ! -f "$PLIST_SRC" ]; then
  echo "[install] missing $PLIST_SRC" >&2
  exit 1
fi

# 先确保 start.sh 跑过一次：venv 装好、依赖装好、首次模型下载
(cd "$HERE/.." && bash ./start.sh)

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

# unload 旧版（若有）再 load
launchctl unload -w "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"

echo "[install] loaded $PLIST_DST"
echo "[install] verify with:  launchctl list | grep whisper-server"
echo "[install] logs at:      tail -f '$HERE/../logs/launchd.out.log'"