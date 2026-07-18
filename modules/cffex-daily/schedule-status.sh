#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.yuque.cffex-daily"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"
CONFIG="$ROOT/modules/cffex-daily/config.json"

echo "=== LaunchAgent ==="
if [[ -f "$PLIST_DST" ]]; then
  echo "plist: $PLIST_DST"
  /usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval' "$PLIST_DST" 2>/dev/null || true
  launchctl print "gui/${UID_NUM}/${LABEL}" 2>/dev/null | head -40 || echo "(not loaded)"
else
  echo "plist: not installed"
fi

echo
echo "=== config schedule ==="
python3 "$ROOT/modules/cffex-daily/set_auto_publish.py" status
