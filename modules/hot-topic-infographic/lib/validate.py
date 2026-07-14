#!/usr/bin/env python3
"""Validate topic JSON against schema and length constraints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCHEMA_PATH, find_topic_json


def validate_topic(data: dict) -> list[str]:
    errors: list[str] = []

    if jsonschema and SCHEMA_PATH.exists():
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: e.path):
            path = ".".join(str(p) for p in err.path) or "(root)"
            errors.append(f"{path}: {err.message}")

    header = data.get("header", {})
    if len(header.get("title", "")) > 18:
        errors.append("header.title exceeds 18 chars")
    if len(header.get("subtitle", "")) > 24:
        errors.append("header.subtitle exceeds 24 chars")

    cards = data.get("cards", [])
    if len(cards) != 4:
        errors.append("cards must contain exactly 4 items")

    for i, card in enumerate(cards):
        for j, bullet in enumerate(card.get("bullets", [])):
            if len(bullet) > 14:
                errors.append(f"cards[{i}].bullets[{j}] exceeds 14 chars: {bullet!r}")
        if len(card.get("bubble", "")) > 16:
            errors.append(f"cards[{i}].bubble exceeds 16 chars")
        if len(card.get("effect", "")) > 14:
            errors.append(f"cards[{i}].effect exceeds 14 chars")

    hooks = data.get("hooks", [])
    if len(hooks) < 4:
        errors.append("hooks must contain at least 4 items")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate topic JSON")
    parser.add_argument("--id", help="Topic id")
    parser.add_argument("--file", help="Path to topic JSON")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
    elif args.id:
        path = find_topic_json(args.id)
    else:
        parser.error("Provide --id or --file")

    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_topic(data)
    if errors:
        print(f"INVALID: {path}")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"OK: {path}")


if __name__ == "__main__":
    main()
