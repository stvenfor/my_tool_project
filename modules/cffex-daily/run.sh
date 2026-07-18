#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODULE="$ROOT/modules/cffex-daily"
CONFIG="$MODULE/config.json"
LOG_DIR="$MODULE/work/logs"
mkdir -p "$LOG_DIR"

TODAY="$(date +%Y%m%d)"
LOG_FILE="$LOG_DIR/daily-$TODAY.log"

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

cd "$ROOT"

# Ensure Homebrew / nvm node if present for launchd (minimal PATH)
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

# Load API key for imagegen if available (do not log secrets)
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ -f "$HOME/.codex/.env" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$HOME/.codex/.env" 2>/dev/null || true
    set +a
  fi
  if [[ -z "${OPENAI_API_KEY:-}" && -f "$HOME/.zshenv" ]]; then
    # shellcheck disable=SC1090
    source "$HOME/.zshenv" 2>/dev/null || true
  fi
fi

AUTO="$(python3 - <<'PY' "$CONFIG"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("1" if cfg.get("schedule", {}).get("auto_publish", True) else "0")
PY
)"

if [[ "$AUTO" != "1" ]]; then
  log "schedule disabled (auto_publish=false); skip generate/beautify/publish"
  exit 0
fi

log "=== CFFEX daily pipeline start ==="

log "Step 1: generate report"
set +e
python3 "$MODULE/fetch_and_render.py" "$@" >>"$LOG_FILE" 2>&1
GEN_STATUS=$?
set -e

if [[ $GEN_STATUS -ne 0 ]]; then
  log "generate failed status=$GEN_STATUS"
  exit "$GEN_STATUS"
fi

PNG="$MODULE/work/output/citic-net-positions-$TODAY.png"
JSON="$MODULE/work/output/citic-net-positions-$TODAY.json"

if [[ ! -f "$PNG" || ! -f "$JSON" ]]; then
  log "no report for $TODAY (weekend/non-trading/skipped); skip beautify+publish"
  exit 0
fi

log "Step 2: beautify"
set +e
python3 "$MODULE/beautify_report.py" --date "$TODAY" --config "$CONFIG" >>"$LOG_FILE" 2>&1
BEAU_STATUS=$?
set -e
if [[ $BEAU_STATUS -ne 0 ]]; then
  log "beautify failed status=$BEAU_STATUS"
  exit "$BEAU_STATUS"
fi

BEAUTIFIED="$(
  python3 - <<'PY' "$MODULE/work/output" "$TODAY" "$CONFIG"
import json, re, sys
from pathlib import Path
from datetime import datetime
out_root = Path(sys.argv[1])
day = sys.argv[2]
cfg = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
beautify = cfg.get("beautify") or {}
rel = beautify.get("output_dir", "_hot-topic-infographic/beautified")
out_dir = Path(rel)
if not out_dir.is_absolute():
    out_dir = Path(sys.argv[3]).resolve().parents[2] / rel
trade = datetime.strptime(day, "%Y%m%d").date()
stem = f"cffex-position-report-{trade:%Y-%m-%d}-auto"
cands = sorted(out_dir.glob(f"{stem}-v*.png"), key=lambda p: p.stat().st_mtime)
if not cands:
    raise SystemExit(f"no beautified image matching {stem}-v*.png")
print(cands[-1])
PY
)"

if [[ ! -f "$BEAUTIFIED" ]]; then
  log "beautified image missing"
  exit 1
fi
log "beautified: $BEAUTIFIED"

log "Step 3: publish imagetext"
set +e
node "$MODULE/publish-imagetext-to-douyin.mjs" \
  --date "$TODAY" \
  --image "$BEAUTIFIED" \
  --skip-music >>"$LOG_FILE" 2>&1
PUB_STATUS=$?
set -e

if [[ $PUB_STATUS -ne 0 ]]; then
  log "publish failed status=$PUB_STATUS"
  exit "$PUB_STATUS"
fi

log "=== CFFEX daily pipeline done ==="
exit 0
