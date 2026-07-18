#!/usr/bin/env python3
"""Toggle schedule.auto_publish in config.json (on|off|status)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config.json"


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"on", "off", "status"}:
        print("Usage: set_auto_publish.py on|off|status", file=sys.stderr)
        raise SystemExit(2)

    action = sys.argv[1]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    schedule = cfg.setdefault("schedule", {})
    current = bool(schedule.get("auto_publish", True))

    if action == "status":
        print(f"auto_publish={current}")
        print(f"hour={schedule.get('hour', 21)} minute={schedule.get('minute', 0)}")
        return

    schedule["auto_publish"] = action == "on"
    schedule.setdefault("hour", 21)
    schedule.setdefault("minute", 0)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"auto_publish={schedule['auto_publish']}")


if __name__ == "__main__":
    main()
