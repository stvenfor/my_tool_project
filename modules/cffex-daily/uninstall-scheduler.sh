#!/bin/zsh
set -euo pipefail

LABEL="com.yuque.cffex-daily"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"

launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
rm -f "$PLIST_DST"

echo "Uninstalled scheduler: $LABEL"
echo "Manual runs still work via npm run cffex:daily / cffex:beautify / cffex:publish-imagetext"
