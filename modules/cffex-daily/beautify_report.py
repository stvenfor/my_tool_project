#!/usr/bin/env python3
"""Beautify CFFEX daily report PNG via OpenAI gpt-image-2 edit CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = MODULE_DIR / "config.json"
SYMBOLS = ("IH", "IF", "IC", "IM")


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(raw: str) -> Path:
    expanded = os.path.expanduser(raw)
    p = Path(expanded)
    if p.is_absolute():
        return p
    return (ROOT / p).resolve()


def output_dir_from_config(cfg: dict) -> Path:
    rel = cfg.get("output_dir", "modules/cffex-daily/work/output")
    return resolve_path(rel)


def format_signed(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


def format_stock_value(n: int) -> str:
    if abs(n) >= 10000:
        return f"{n / 10000:.1f}万"
    return f"{n:,}"


def peak_symbol(by_symbol: dict) -> tuple[str, int]:
    peak = max(SYMBOLS, key=lambda s: abs(int(by_symbol[s])))
    return peak, int(by_symbol[peak])


def build_prompt(report: dict) -> str:
    by_symbol = report["citic_by_symbol"]
    peak, peak_val = peak_symbol(by_symbol)
    peak_dir = "加多" if peak_val >= 0 else "加空"
    peak_abs = f"{abs(peak_val):,}"
    logo = report.get("logo_handle", "@小水獭学AI")
    cards = "；".join(
        f"{s} {format_signed(int(by_symbol[s]))}（{'加多' if int(by_symbol[s]) >= 0 else '加空'}）"
        for s in SYMBOLS
    )
    total = int(report["citic_total"])
    top20 = int(report["top20_net_short_total"])
    net_buy = int(report["net_buy_total"])

    return f"""模板：Infographic Engine / 信息图引擎（case 334、case 1、case 8）

任务：中文金融数据日报竖版信息图（抖音 9:16），商务 PPT 精修风。

参考图角色：
- 图1：唯一版式/视觉风格参考（白底、细线分区、深蓝标题编号、红=加多、青绿=加空、扁平图表）
- 图2：唯一数据与文案来源；日期、中文、数值、柱向、署名必须以图2为准

构图（自上而下）：
1. 页眉：左「中信期货 · 净持仓日报」；大号日期「{report["date_label"]}」；副标题「来源于网络 · 机构持仓数据」；右上圆形头像 +「{logo}」
2. 今日要点浅红横幅：今日要点 · {peak} {peak_dir} {peak_abs} 手为最大边际变化
3. 01 各品种净持仓：四列卡片 — {cards}
4. 02 持仓变化对比：正负柱图，平方根刻度，图例加多/加空，数值标签不重叠；柱向与上表一致
5. 03 市场概览：中信整体 {format_signed(total)}；前20机构净空单（存量）{format_stock_value(top20)}（全市场存量 · {top20:,} 手）；今日净买入 {format_signed(net_buy)}
6. footer：数据来源于网络，仅供参考 · 投资有风险，入市需谨慎

视觉：白底、克制阴影、对齐网格、充足留白；禁止花哨装饰、乱码、错数、文字重叠。
比例：9:16 竖版高清 PNG。
"""


def next_output_path(out_dir: Path, trade_date: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"cffex-position-report-{trade_date:%Y-%m-%d}-auto"
    existing = list(out_dir.glob(f"{stem}-v*.png"))
    versions: list[int] = []
    for p in existing:
        m = re.search(r"-v(\d+)\.png$", p.name)
        if m:
            versions.append(int(m.group(1)))
    n = max(versions, default=0) + 1
    return out_dir / f"{stem}-v{n}.png"


def run_image_gen(
    cli: Path,
    style_ref: Path,
    base_png: Path,
    prompt: str,
    out_path: Path,
    model: str,
    size: str,
    quality: str,
) -> None:
    if not cli.is_file():
        raise SystemExit(f"image_gen CLI not found: {cli}")
    if not style_ref.is_file():
        raise SystemExit(f"style_reference not found: {style_ref}")
    if not base_png.is_file():
        raise SystemExit(f"base PNG not found: {base_png}")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(prompt)
        prompt_file = Path(tf.name)

    cmd = [
        sys.executable,
        str(cli),
        "edit",
        "--image",
        str(style_ref),
        "--image",
        str(base_png),
        "--prompt-file",
        str(prompt_file),
        "--model",
        model,
        "--size",
        size,
        "--quality",
        quality,
        "--out",
        str(out_path),
    ]
    try:
        print("Running:", " ".join(cmd))
        result = subprocess.run(cmd, cwd=str(ROOT), check=False)
        if result.returncode != 0:
            raise SystemExit(f"image_gen failed with exit {result.returncode}")
        if not out_path.is_file():
            raise SystemExit(f"image_gen finished but output missing: {out_path}")
    finally:
        prompt_file.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Beautify CFFEX daily report for Douyin")
    parser.add_argument("--date", help="Trade date YYYYMMDD (default: today)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true", help="Print prompt/paths only")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    beautify = cfg.get("beautify") or {}
    if not beautify.get("enabled", True):
        print("beautify.enabled=false; skip")
        return

    if args.date:
        trade_date = datetime.strptime(args.date, "%Y%m%d").date()
    else:
        trade_date = date.today()

    out_root = output_dir_from_config(cfg)
    json_path = out_root / f"citic-net-positions-{trade_date:%Y%m%d}.json"
    png_path = out_root / f"citic-net-positions-{trade_date:%Y%m%d}.png"
    if not json_path.is_file():
        raise SystemExit(f"Report JSON not found: {json_path}")
    if not png_path.is_file():
        raise SystemExit(f"Report PNG not found: {png_path}")

    report = json.loads(json_path.read_text(encoding="utf-8"))
    prompt = build_prompt(report)

    style_ref = resolve_path(
        beautify.get(
            "style_reference",
            "_hot-topic-infographic/beautified/cffex-position-report-2026-07-14-cursor-v1.png",
        )
    )
    out_dir = resolve_path(beautify.get("output_dir", "_hot-topic-infographic/beautified"))
    out_path = next_output_path(out_dir, trade_date)
    cli = resolve_path(
        beautify.get(
            "image_gen_cli",
            "~/.codex/skills/.system/imagegen/scripts/image_gen.py",
        )
    )
    model = beautify.get("model", "gpt-image-2")
    size = beautify.get("size", "1024x1536")
    quality = beautify.get("quality", "high")

    if args.dry_run:
        print("--- dry-run ---")
        print("style_ref:", style_ref)
        print("base_png:", png_path)
        print("out:", out_path)
        print("cli:", cli)
        print("model/size/quality:", model, size, quality)
        print("--- prompt ---")
        print(prompt)
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set")

    run_image_gen(cli, style_ref, png_path, prompt, out_path, model, size, quality)
    print(f"Saved beautified: {out_path}")


if __name__ == "__main__":
    main()
