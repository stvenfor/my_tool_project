#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$ROOT/scripts/cffex-daily/com.yuque.cffex-daily.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.yuque.cffex-daily.plist"

mkdir -p "$ROOT/_cffex/logs"
chmod +x "$ROOT/scripts/cffex-daily/run.sh"

launchctl bootout "gui/$(id -u)/com.yuque.cffex-daily" 2>/dev/null || true
cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.yuque.cffex-daily"
launchctl kickstart -k "gui/$(id -u)/com.yuque.cffex-daily" 2>/dev/null || true

echo "Installed scheduler: $PLIST_DST"
echo "It will run every day at 22:00."
echo "Manual run: npm run cffex:daily"
