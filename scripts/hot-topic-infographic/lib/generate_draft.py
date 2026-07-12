#!/usr/bin/env python3
"""Generate draft topic JSON via LLM from hot keywords."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCRIPT_DIR
from topic_llm import generate_topic_data
from validate import validate_topic as run_validate


def generate_draft(keywords: str, theme: str, topic_id: str, use_llm: bool = True) -> Path:
    out_dir = SCRIPT_DIR / "topics" / "draft"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{topic_id}.json"

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    data, source = generate_topic_data(
        topic_id=topic_id,
        theme=theme,
        keywords=kw_list,
        use_llm=use_llm,
    )
    print(f"Source: {source}")

    errors = run_validate(data)
    if errors:
        print("Warning: draft has validation issues:")
        for err in errors:
            print(f"  - {err}")

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved draft: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draft topic JSON")
    parser.add_argument("--keywords", required=True, help="Comma-separated hot keywords")
    parser.add_argument("--theme", required=True, help="Topic theme name")
    parser.add_argument("--id", required=True, help="Topic id slug")
    parser.add_argument("--no-llm", action="store_true", help="Use fallback template only")
    args = parser.parse_args()
    generate_draft(args.keywords, args.theme, args.id, use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
