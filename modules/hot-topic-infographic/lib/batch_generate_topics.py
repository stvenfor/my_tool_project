#!/usr/bin/env python3
"""Batch generate draft topic JSON by identity/relationship category."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SCRIPT_DIR, load_categories
from topic_llm import build_category_system_prompt, generate_topic_data
from validate import validate_topic


def existing_topic_ids() -> set[str]:
    ids: set[str] = set()
    for subdir in ("draft", "approved"):
        folder = SCRIPT_DIR / "topics" / subdir
        if folder.exists():
            for path in folder.glob("*.json"):
                ids.add(path.stem)
    return ids


def select_pilot_topics(category_slug: str, category_cfg: dict, count: int) -> list[dict]:
    pilot = category_cfg.get("pilot_topics", [])
    if pilot:
        return pilot[:count]

    angles = category_cfg.get("angles", [])
    selected = []
    for i, angle in enumerate(angles[:count]):
        slug = angle.lower().replace(" ", "-")
        topic_id = f"{category_slug}-{slug}-2026"
        selected.append(
            {
                "id": topic_id,
                "angle": angle,
                "keywords": [angle, category_cfg.get("label", category_slug)],
                "card_hints": [],
            }
        )
    return selected


def save_draft(topic_id: str, data: dict, invalid: bool = False) -> Path:
    out_dir = SCRIPT_DIR / "topics" / "draft"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_INVALID" if invalid else ""
    out_path = out_dir / f"{topic_id}{suffix}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def write_report(report_path: Path, results: list[dict]) -> None:
    lines = [
        f"# 批量话题生成报告",
        f"",
        f"日期：{date.today().isoformat()}",
        f"",
        f"## 汇总",
        f"",
        f"| 状态 | 数量 |",
        f"|------|------|",
    ]
    ok = sum(1 for r in results if r["status"] == "ok")
    invalid = sum(1 for r in results if r["status"] == "invalid")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    lines += [
        f"| 成功 | {ok} |",
        f"| 校验失败 | {invalid} |",
        f"| 跳过 | {skipped} |",
        f"",
        f"## 明细",
        f"",
        f"| 类别 | id | 角度 | 状态 | 来源 | 备注 |",
        f"|------|-----|------|------|------|------|",
    ]
    for r in results:
        lines.append(
            f"| {r['category']} | {r['id']} | {r['angle']} | {r['status']} | {r['source']} | {r['note']} |"
        )
    if invalid:
        lines += ["", "## 校验错误", ""]
        for r in results:
            if r["status"] == "invalid" and r.get("errors"):
                lines.append(f"### {r['id']}")
                for err in r["errors"]:
                    lines.append(f"- {err}")
                lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def generate_one(
    category_slug: str,
    category_cfg: dict,
    seed: dict,
    *,
    use_llm: bool,
    retries: int = 1,
) -> dict:
    topic_id = seed["id"]
    angle = seed.get("angle", "")
    keywords = seed.get("keywords", [])
    card_hints = seed.get("card_hints", [])
    label = category_cfg.get("label", category_slug)
    framing = category_cfg.get("framing", "")
    theme = f"{label}{angle}" if angle else label

    system_prompt = build_category_system_prompt(category_slug, category_cfg)
    extra_context = (
        f"请围绕「{angle}」角度创作，四格递进。\n"
        f"header.title 建议包含「{label}」或「{angle}」相关表述。\n"
        f"不要与「职场禁忌四件套」(workplace-taboo) 重复。\n"
    )

    last_errors: list[str] = []
    source = "fallback"
    data: dict = {}

    for attempt in range(retries + 1):
        data, source = generate_topic_data(
            topic_id=topic_id,
            theme=theme,
            keywords=keywords,
            use_llm=use_llm,
            system_prompt=system_prompt,
            extra_context=extra_context,
            category_slug=category_slug,
            angle=angle,
            framing=framing,
            card_hints=card_hints,
        )
        last_errors = validate_topic(data)
        if not last_errors:
            break
        if attempt < retries:
            extra_context += f"\n上次校验失败：{'; '.join(last_errors[:5])}。请修正字数和字段。\n"

    result = {
        "category": label,
        "id": topic_id,
        "angle": angle,
        "source": source,
        "errors": last_errors,
    }

    if last_errors:
        save_draft(topic_id, data, invalid=True)
        result["status"] = "invalid"
        result["note"] = f"{len(last_errors)} validation errors"
    else:
        save_draft(topic_id, data)
        result["status"] = "ok"
        result["note"] = "validated"

    return result


def run_batch(
    category_slugs: list[str],
    *,
    count: int = 3,
    use_llm: bool = True,
    all_categories: bool = False,
) -> list[dict]:
    categories = load_categories()
    if not categories:
        raise SystemExit("categories.json not found or empty")

    if all_categories:
        category_slugs = list(categories.keys())

    existing = existing_topic_ids()
    results: list[dict] = []

    for slug in category_slugs:
        if slug not in categories:
            print(f"Unknown category: {slug}")
            continue
        cfg = categories[slug]
        status = cfg.get("status", "pending")
        if status == "pending" and not cfg.get("pilot_topics"):
            print(f"Skipping pending category without pilot_topics: {slug}")
            continue

        seeds = select_pilot_topics(slug, cfg, count)
        print(f"\n=== {cfg.get('label', slug)} ({len(seeds)} topics) ===")

        for seed in seeds:
            topic_id = seed["id"]
            if topic_id in existing:
                print(f"Skip existing: {topic_id}")
                results.append(
                    {
                        "category": cfg.get("label", slug),
                        "id": topic_id,
                        "angle": seed.get("angle", ""),
                        "status": "skipped",
                        "source": "-",
                        "note": "already exists",
                        "errors": [],
                    }
                )
                continue

            print(f"Generating: {topic_id} ({seed.get('angle', '')})")
            result = generate_one(slug, cfg, seed, use_llm=use_llm)
            results.append(result)
            status_icon = "OK" if result["status"] == "ok" else result["status"].upper()
            print(f"  -> {status_icon} ({result['source']})")

    report_path = SCRIPT_DIR / "topics" / f"batch-report-{date.today().isoformat()}.md"
    write_report(report_path, results)
    print(f"\nReport: {report_path}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch generate draft topics by category")
    parser.add_argument("--categories", help="Comma-separated category slugs, e.g. worker,family")
    parser.add_argument("--all", action="store_true", help="Process all non-pending categories")
    parser.add_argument("--count", type=int, default=3, help="Topics per category (default 3)")
    parser.add_argument("--no-llm", action="store_true", help="Use fallback template only")
    args = parser.parse_args()

    if not args.all and not args.categories:
        parser.error("Provide --categories or --all")

    slugs = [s.strip() for s in (args.categories or "").split(",") if s.strip()]
    results = run_batch(slugs, count=args.count, use_llm=not args.no_llm, all_categories=args.all)

    failed = [r for r in results if r["status"] == "invalid"]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
