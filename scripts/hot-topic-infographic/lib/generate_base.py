#!/usr/bin/env python3
"""Generate base images via OpenAI Images API (no Chinese text)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ai_prompt import build_prompt
from common import load_config, load_topic, load_topic_layout, sync_topic_to_output, topic_paths


def call_openai_image(prompt: str, cfg: dict) -> bytes:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set")

    payload = {
        "model": cfg.get("openai_model", "gpt-image-1"),
        "prompt": prompt,
        "size": cfg.get("openai_image_size", "1024x1792"),
        "n": 1,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API error {exc.code}: {body}") from exc

    item = result["data"][0]
    if "b64_json" in item:
        return base64.b64decode(item["b64_json"])
    if "url" in item:
        with urllib.request.urlopen(item["url"], timeout=120) as img_resp:
            return img_resp.read()
    raise SystemExit("Unexpected OpenAI response: no image data")


def generate_single_base(topic_id: str, force: bool = False) -> Path:
    paths = topic_paths(topic_id)
    if paths["base_png"].exists() and not force:
        print(f"Skip existing base: {paths['base_png']}")
        return paths["base_png"]

    cfg = load_config()
    topic = load_topic(topic_id)
    try:
        layout = load_topic_layout(topic_id)
    except FileNotFoundError:
        from generate_layout import generate_layout

        generate_layout(topic_id)
        layout = load_topic_layout(topic_id)

    prompt = build_prompt(topic, layout, mode="single")
    paths["base_png"].write_bytes(call_openai_image(prompt, cfg))
    print(f"Saved base: {paths['base_png']}")
    return paths["base_png"]


def generate_carousel_bases(topic_id: str, force: bool = False) -> list[Path]:
    paths = topic_paths(topic_id)
    paths["carousel_base_dir"].mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    topic = load_topic(topic_id)
    layout = load_topic_layout(topic_id)
    outputs = []

    for idx in range(5):
        out = paths["carousel_base_dir"] / f"base-{idx:02d}.png"
        if out.exists() and not force:
            print(f"Skip existing: {out}")
            outputs.append(out)
            continue
        prompt = build_prompt(topic, layout, mode="carousel", slide_index=idx)
        out.write_bytes(call_openai_image(prompt, cfg))
        print(f"Saved carousel base: {out}")
        outputs.append(out)
    return outputs


def generate_base(topic_id: str, mode: str = "both", force: bool = False) -> dict:
    sync_topic_to_output(topic_id)
    paths = topic_paths(topic_id)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    result: dict = {}
    if mode in ("single", "both"):
        result["single"] = generate_single_base(topic_id, force=force)
    if mode in ("carousel", "both"):
        result["carousel"] = generate_carousel_bases(topic_id, force=force)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI base images")
    parser.add_argument("--id", required=True)
    parser.add_argument("--mode", choices=["single", "carousel", "both"], default="both")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    generate_base(args.id, mode=args.mode, force=args.force)


if __name__ == "__main__":
    main()
