#!/usr/bin/env bash
set -euo pipefail

PLIST_DST="$HOME/Library/LaunchAgents/com.bobo.whisper-server.plist"

if [ -f "$PLIST_DST" ]; then
  launchctl unload -w "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "[uninstall] removed $PLIST_DST"
else
  echo "[uninstall] $PLIST_DST not present, nothing to do"
fi