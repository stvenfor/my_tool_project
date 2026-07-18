#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$ROOT/modules/cffex-daily/com.yuque.cffex-daily.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.yuque.cffex-daily.plist"
LABEL="com.yuque.cffex-daily"
UID_NUM="$(id -u)"

mkdir -p "$ROOT/modules/cffex-daily/work/logs"
chmod +x "$ROOT/modules/cffex-daily/run.sh"
chmod +x "$ROOT/modules/cffex-daily/uninstall-scheduler.sh" 2>/dev/null || true

# Rewrite plist paths for current machine / project root
python3 - <<PY
from pathlib import Path
root = Path("$ROOT")
src = Path("$PLIST_SRC")
text = src.read_text(encoding="utf-8")
# Keep label; replace hardcoded paths with current ROOT
old_root = "/Users/mac/Desktop/github/my_tool_project"
text = text.replace(old_root, str(root))
dst = Path("$PLIST_DST")
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(text, encoding="utf-8")
print(f"Wrote {dst}")
PY

launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/${UID_NUM}" "$PLIST_DST"
launchctl enable "gui/${UID_NUM}/${LABEL}"

echo "Installed scheduler: $PLIST_DST"
echo "Runs every calendar day at 21:00 → generate → beautify → Douyin imagetext."
echo "Weekends / non-trading: fetch skips; no publish."
echo "Disable send (keep job): npm run cffex:auto-off"
echo "Uninstall job:         npm run cffex:unschedule"
echo "Manual full run:       $ROOT/modules/cffex-daily/run.sh"
echo "Requires: OPENAI_API_KEY, Douyin login (cffex:auth), Chrome, logged-in GUI session."
