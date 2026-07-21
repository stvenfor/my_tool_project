#!/usr/bin/env python3.12
"""Archive dated canvas + JSON artifacts for each ETF review run.

Copies into:
  modules/etf-monitor/reports/snapshots/YYYY-MM-DD/
    etf-68-status.canvas.tsx
    canvas-data.json
    edge-conditions.json
    representative-technical-review.json   (if present)
    interactive-canvas.html               (if present)
    manifest.json

Also writes dated convenience copies under reports/:
  etf68-canvas-data-YYYY-MM-DD.json
  etf-68-status-YYYY-MM-DD.canvas.tsx
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE_ROOT = Path(__file__).resolve().parent
REPORTS = MODULE_ROOT / "reports"
SNAPSHOTS = REPORTS / "snapshots"
SHANGHAI = ZoneInfo("Asia/Shanghai")

# Cursor IDE canvases live outside the repo
CANVASES_DIR = Path.home() / ".cursor/projects/Users-mac-Desktop-github-my-tool-project/canvases"


def resolve_date(explicit: str | None) -> str:
    if explicit:
        return explicit
    review = REPORTS / "representative-technical-review-2026-07-21.json"
    # Prefer newest representative-technical-review-*.json
    candidates = sorted(REPORTS.glob("representative-technical-review-*.json"))
    if candidates:
        latest = candidates[-1]
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            if data.get("data_date"):
                return str(data["data_date"])
        except (json.JSONDecodeError, OSError):
            pass
        # filename fallback
        stem = latest.stem  # representative-technical-review-YYYY-MM-DD
        parts = stem.rsplit("-", 3)
        if len(parts) >= 4:
            return "-".join(parts[-3:])
    return datetime.now(SHANGHAI).date().isoformat()


def copy_if_exists(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Snapshot date YYYY-MM-DD (default: latest report data_date)")
    parser.add_argument(
        "--canvas",
        type=Path,
        help="Source .canvas.tsx path (default: canvases/etf-68-status-<date>.canvas.tsx)",
    )
    args = parser.parse_args()
    day = resolve_date(args.date)
    snap = SNAPSHOTS / day
    snap.mkdir(parents=True, exist_ok=True)

    canvas_src = args.canvas or (CANVASES_DIR / f"etf-68-status-{day}.canvas.tsx")
    # fallback: any matching canvas
    if not canvas_src.is_file():
        matches = sorted(CANVASES_DIR.glob("etf-68-status-*.canvas.tsx"))
        if matches:
            canvas_src = matches[-1]

    saved: dict[str, str] = {}

    pairs = [
        (canvas_src, snap / "etf-68-status.canvas.tsx", "canvas"),
        (REPORTS / f"_etf68_canvas_data.json", snap / "canvas-data.json", "canvas_data"),
        (REPORTS / f"etf68-canvas-data-{day}.json", snap / "canvas-data.json", "canvas_data_dated"),
        (REPORTS / f"etf68-edge-conditions-{day}.json", snap / "edge-conditions.json", "edge"),
        (
            REPORTS / f"representative-technical-review-{day}.json",
            snap / "representative-technical-review.json",
            "review",
        ),
        (REPORTS / "etf68-interactive-canvas.html", snap / "interactive-canvas.html", "html"),
    ]

    # Prefer dated canvas-data if underscore file is older / missing merge
    # First copy underscore file, then overwrite with dated if present
    for src, dest, key in pairs:
        if copy_if_exists(src, dest):
            saved[key] = str(src)

    # Ensure canvas-data in reports root is also dated
    underscored = REPORTS / "_etf68_canvas_data.json"
    dated_canvas_data = REPORTS / f"etf68-canvas-data-{day}.json"
    if underscored.is_file():
        shutil.copy2(underscored, dated_canvas_data)
        shutil.copy2(underscored, snap / "canvas-data.json")
        saved["canvas_data"] = str(dated_canvas_data)

    # Archive canvas into reports/ as well (git-friendly copy)
    if canvas_src.is_file():
        archived_canvas = REPORTS / f"etf-68-status-{day}.canvas.tsx"
        shutil.copy2(canvas_src, archived_canvas)
        shutil.copy2(canvas_src, snap / "etf-68-status.canvas.tsx")
        saved["canvas"] = str(archived_canvas)
        saved["canvas_live"] = str(canvas_src)

    manifest = {
        "date": day,
        "saved_at": datetime.now(SHANGHAI).isoformat(),
        "snapshot_dir": str(snap),
        "files": {k: v for k, v in saved.items()},
        "snapshot_contents": sorted(p.name for p in snap.iterdir() if p.is_file()),
    }
    (snap / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
