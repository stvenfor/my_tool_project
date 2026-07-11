#!/usr/bin/env python3
"""Fetch CFFEX position data and render a daily CITIC futures report image."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "config.json"
DEFAULT_OUTPUT = ROOT / "_cffex/output"
HTML_TEMPLATE = SCRIPT_DIR / "render_template.html"
LOGO_FILE = SCRIPT_DIR / "logo.png"
DEFAULT_LOGO_HANDLE = "@小水獭学AI"
BGM_FILE = SCRIPT_DIR / "bgm.mp3"
QUOTES_FILE = SCRIPT_DIR / "encouragement_quotes.json"
QUOTE_STATE_FILE = SCRIPT_DIR / "quote_state.json"
CHART_API = "https://antv-studio.alipay.com/api/gpt-vis"
REPORT_WIDTH = 720
REPORT_HEIGHT = 1280

CITIC = "中信期货(代客)"
SYMBOLS = ["IH", "IF", "IC", "IM"]
SYMBOL_NAMES = {
    "IH": "上证50",
    "IF": "沪深300",
    "IC": "中证500",
    "IM": "中证1000",
}
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
DISCLAIMER_LINES = [
    "数据来源于网络，仅供参考",
    "投资有风险，入市需谨慎",
]


def load_config(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "output_dir": str(DEFAULT_OUTPUT),
        "theme": "academy",
        "chart_width": 640,
        "chart_height": 380,
    }


def load_quotes() -> list[str]:
    if QUOTES_FILE.exists():
        return json.loads(QUOTES_FILE.read_text(encoding="utf-8"))
    return ["耐心是投资者最锋利的武器，静待花开！"]


def load_quote_state() -> dict:
    if QUOTE_STATE_FILE.exists():
        return json.loads(QUOTE_STATE_FILE.read_text(encoding="utf-8"))
    return {"assignments": {}, "used": []}


def save_quote_state(state: dict) -> None:
    QUOTE_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_daily_quote(trade_date: date) -> str:
    quotes = load_quotes()
    state = load_quote_state()
    date_key = trade_date.strftime("%Y%m%d")
    assignments: dict[str, str] = state.setdefault("assignments", {})
    used: list[str] = state.setdefault("used", [])

    if date_key in assignments:
        return assignments[date_key]

    available = [q for q in quotes if q not in used]
    if not available:
        used.clear()
        available = quotes[:]

    index = int(date_key) % len(available)
    quote = available[index]
    used.append(quote)
    assignments[date_key] = quote
    save_quote_state(state)
    return quote


def pick_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        font_path = Path(candidate)
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def fetch_csv(symbol: str, trade_date: date) -> str:
    y = trade_date.strftime("%Y")
    m = trade_date.strftime("%m")
    d = trade_date.strftime("%d")
    url = f"http://www.cffex.com.cn/sj/ccpm/{y}{m}/{d}/{symbol}_1.csv"
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode("gbk")


def parse_rows(csv_text: str) -> list[list[str]]:
    reader = csv.reader(StringIO(csv_text.strip()))
    next(reader, None)
    next(reader, None)
    return [row for row in reader if len(row) >= 12]


def citic_net_change(rows: list[list[str]]) -> int:
    long_change = 0
    short_change = 0
    for row in rows:
        if row[6] == CITIC:
            long_change += int(row[8])
        if row[9] == CITIC:
            short_change += int(row[11])
    return long_change - short_change


def top20_net_short_total(rows: list[list[str]]) -> int:
    long_pos = 0
    short_pos = 0
    for row in rows:
        if int(row[2]) <= 20:
            long_pos += int(row[7])
            short_pos += int(row[10])
    return short_pos - long_pos


def all_members_net_buy(rows: list[list[str]]) -> int:
    members: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        members[row[6]][0] += int(row[8])
        members[row[9]][1] += int(row[11])
    return sum(long_change - short_change for long_change, short_change in members.values())


def format_net_change(net: int) -> str:
    if net >= 0:
        return f"净加{net}手 多单"
    return f"净加{abs(net)}手 空单"


def format_overall(total: int) -> str:
    if total >= 0:
        return f"加多单{total}手"
    return f"加空单{abs(total)}手"


def format_date_label(trade_date: date) -> str:
    return f"{trade_date:%Y年%m月%d日} {WEEKDAYS[trade_date.weekday()]}"


def resolve_trade_date(explicit: str | None) -> date:
    if explicit:
        return datetime.strptime(explicit, "%Y%m%d").date()
    return date.today()


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def fetch_report(trade_date: date) -> dict:
    symbol_rows: dict[str, list[list[str]]] = {}
    for symbol in SYMBOLS:
        csv_text = fetch_csv(symbol, trade_date)
        rows = parse_rows(csv_text)
        if not rows:
            raise RuntimeError(f"{symbol} has no ranking rows for {trade_date:%Y%m%d}")
        symbol_rows[symbol] = rows

    citic_by_symbol = {symbol: citic_net_change(rows) for symbol, rows in symbol_rows.items()}
    citic_total = sum(citic_by_symbol.values())
    top20_total = sum(top20_net_short_total(rows) for rows in symbol_rows.values())
    net_buy_total = sum(all_members_net_buy(rows) for rows in symbol_rows.values())

    return {
        "trade_date": trade_date.strftime("%Y%m%d"),
        "date_label": format_date_label(trade_date),
        "daily_quote": pick_daily_quote(trade_date),
        "citic_by_symbol": citic_by_symbol,
        "citic_total": citic_total,
        "top20_net_short_total": top20_total,
        "net_buy_total": net_buy_total,
    }


MORANDI_LONG = "#d14d4d"
MORANDI_LONG_DEEP = "#b83333"
MORANDI_SHORT = "#3a9a6a"
MORANDI_SHORT_DEEP = "#257a52"
MORANDI_PALETTE = ["#a8b5c4", "#9b8aa5", "#c4847a", "#7ba38c"]


def build_chart_svg(report: dict, width: int = 632, height: int = 260) -> str:
    """Editorial column chart with zone tints, gradients, and inline labels."""
    values = [report["citic_by_symbol"][s] for s in SYMBOLS]
    max_abs = max(abs(v) for v in values) or 1
    max_idx = max(range(len(values)), key=lambda i: abs(values[i]))

    pad_top, pad_bottom, pad_x = 32, 52, 28
    chart_w = width - pad_x * 2
    chart_h = height - pad_top - pad_bottom
    zero_y = pad_top + chart_h / 2
    bar_w = chart_w / len(SYMBOLS) * 0.48
    gap = chart_w / len(SYMBOLS)

    defs = (
        "<defs>"
        '<linearGradient id="gradLong" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{MORANDI_LONG}"/>'
        f'<stop offset="100%" stop-color="{MORANDI_LONG_DEEP}"/>'
        "</linearGradient>"
        '<linearGradient id="gradShort" x1="0" y1="1" x2="0" y2="0">'
        f'<stop offset="0%" stop-color="{MORANDI_SHORT}"/>'
        f'<stop offset="100%" stop-color="{MORANDI_SHORT_DEEP}"/>'
        "</linearGradient>"
        "</defs>"
    )

    zones = (
        f'<rect x="{pad_x}" y="{pad_top}" width="{chart_w}" height="{chart_h / 2}" '
        f'fill="rgba(209,77,77,0.10)" rx="4"/>'
        f'<rect x="{pad_x}" y="{zero_y}" width="{chart_w}" height="{chart_h / 2}" '
        f'fill="rgba(58,154,106,0.10)" rx="4"/>'
    )

    grid_lines: list[str] = []
    for frac in (-0.5, 0.5):
        y = zero_y - frac * chart_h
        grid_lines.append(
            f'<line x1="{pad_x}" y1="{y:.1f}" x2="{width - pad_x}" y2="{y:.1f}" '
            f'stroke="#ebebeb" stroke-width="1" stroke-dasharray="4,4"/>'
        )

    bars: list[str] = []
    labels: list[str] = []
    for i, symbol in enumerate(SYMBOLS):
        val = values[i]
        cx = pad_x + gap * i + gap / 2
        bar_h = (abs(val) / max_abs) * (chart_h / 2 - 16)
        is_long = val >= 0
        fill = "url(#gradLong)" if is_long else "url(#gradShort)"
        color = MORANDI_LONG_DEEP if is_long else MORANDI_SHORT_DEEP
        x = cx - bar_w / 2
        rx = 4 if bar_h > 6 else 1

        if is_long:
            y = zero_y - bar_h
            label_y = y - 10
        else:
            y = zero_y
            label_y = y + bar_h + 18

        highlight = ""
        if i == max_idx:
            highlight = (
                f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="{bar_w + 8:.1f}" '
                f'height="{bar_h + 8:.1f}" fill="none" stroke="{color}" stroke-width="1.5" '
                f'rx="6" opacity="0.35"/>'
            )

        bars.append(
            f"{highlight}"
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'fill="{fill}" rx="{rx}"/>'
        )

        sign = "+" if val >= 0 else ""
        labels.append(
            f'<text x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
            f'font-family="Helvetica Neue, PingFang SC, sans-serif" font-size="13" '
            f'font-weight="800" fill="{color}">{sign}{val:,}</text>'
        )
        labels.append(
            f'<text x="{cx:.1f}" y="{height - 28}" text-anchor="middle" '
            f'font-family="Helvetica Neue, PingFang SC, sans-serif" font-size="12" '
            f'font-weight="700" fill="#1a1a1a">{symbol}</text>'
        )
        labels.append(
            f'<text x="{cx:.1f}" y="{height - 12}" text-anchor="middle" '
            f'font-family="Helvetica Neue, PingFang SC, sans-serif" font-size="10" '
            f'fill="#8c8c8c">{SYMBOL_NAMES[symbol]}</text>'
        )

    zero_line = (
        f'<line x1="{pad_x}" y1="{zero_y:.1f}" x2="{width - pad_x}" y2="{zero_y:.1f}" '
        f'stroke="#d9d9d9" stroke-width="1.5"/>'
    )

    return (
        f'<div class="chart-wrap"><svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="持仓变化对比">'
        f"{defs}{zones}{''.join(grid_lines)}{zero_line}{''.join(bars)}{''.join(labels)}"
        f"</svg></div>"
    )


def fetch_chart_url(report: dict, config: dict) -> str | None:
    """Legacy AntV chart — kept as fallback only."""
    chart_data = [
        {
            "category": f"{symbol} {SYMBOL_NAMES[symbol]}",
            "value": report["citic_by_symbol"][symbol],
        }
        for symbol in SYMBOLS
    ]
    payload = {
        "type": "column",
        "source": "chart-visualization-skills",
        "title": "",
        "theme": "default",
        "width": config.get("chart_width", 640),
        "height": config.get("chart_height", 320),
        "data": chart_data,
        "axisXTitle": "",
        "axisYTitle": "",
        "group": False,
    }
    request = urllib.request.Request(
        CHART_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Chart API unavailable, fallback rendering will be used: {exc}", file=sys.stderr)
        return None

    if not result.get("success"):
        print(f"Chart API failed: {result}", file=sys.stderr)
        return None
    return result.get("resultObj")


def download_chart_image(chart_url: str, output_path: Path) -> bool:
    try:
        with urllib.request.urlopen(chart_url, timeout=30) as response:
            output_path.write_bytes(response.read())
        return True
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Failed to download chart image: {exc}", file=sys.stderr)
        return False


def image_to_data_uri(image_path: Path) -> str:
    suffix = image_path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def format_symbol_value(net: int) -> str:
    sign = "+" if net >= 0 else ""
    return f"{sign}{net:,}"


def build_symbol_cards(report: dict) -> str:
    cards: list[str] = []
    for symbol in SYMBOLS:
        net = report["citic_by_symbol"][symbol]
        css_class = "long" if net >= 0 else "short"
        direction = "净加多" if net >= 0 else "净加空"
        badge = "↑ 加多" if net >= 0 else "↓ 加空"
        cards.append(
            f'<div class="symbol-cell {css_class}">'
            f'<span class="sym-watermark">{symbol}</span>'
            f'<div class="sym-top">'
            f'<span class="sym-label">{symbol} · {SYMBOL_NAMES[symbol]}</span>'
            f'<span class="dir-badge {css_class}">{badge}</span>'
            f"</div>"
            f'<div class="sym-value">{format_symbol_value(net)}</div>'
            f'<div class="sym-sub">{direction} {abs(net):,}手</div>'
            f"</div>"
        )
    return "\n        ".join(cards)


def load_logo_uri() -> str:
    if LOGO_FILE.exists():
        return image_to_data_uri(LOGO_FILE)
    return ""


def build_html(report: dict, config: dict, chart_url: str | None, work_dir: Path) -> str:
    template = HTML_TEMPLATE.read_text(encoding="utf-8")
    chart_section = build_chart_svg(report)
    logo_src = load_logo_uri()
    logo_handle = config.get("logo_handle", DEFAULT_LOGO_HANDLE)

    citic_total = report["citic_total"]
    replacements = {
        "TITLE": report["daily_quote"],
        "DATE_LABEL": report["date_label"],
        "SYMBOL_CARDS": build_symbol_cards(report),
        "CHART_SECTION": chart_section,
        "LOGO_SECTION": (
            f'<div class="logo-block">'
            f'<img class="logo" src="{logo_src}" width="60" height="60" alt="logo" />'
            f'<span class="logo-handle">{logo_handle}</span>'
            f"</div>"
            if logo_src
            else ""
        ),
        "CITIC_OVERALL": format_symbol_value(citic_total),
        "CITIC_CLASS": "long" if citic_total >= 0 else "short",
        "TOP20_TOTAL": f"{report['top20_net_short_total']:,}",
        "NET_BUY": f"{report['net_buy_total']:,}",
    }
    html = template
    for key, value in replacements.items():
        html = html.replace(f"{{{{{key}}}}}", value)
    return html


def render_with_playwright(html: str, output_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not available, using Pillow fallback.", file=sys.stderr)
        return False

    html_path = output_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": REPORT_WIDTH, "height": REPORT_HEIGHT})
            page.set_content(html, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(500)
            page.locator(".report").screenshot(path=str(output_path), type="png")
            browser.close()
        return True
    except Exception as exc:
        print(f"Playwright render failed, using Pillow fallback: {exc}", file=sys.stderr)
        return False


def render_fallback_image(report: dict, config: dict, output_path: Path, chart_path: Path | None = None) -> None:
    width, height = REPORT_WIDTH, REPORT_HEIGHT
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)

    header_height = 150
    draw.rectangle((0, 0, width, header_height), fill="#2563eb")
    title_font = pick_font(34)
    date_font = pick_font(20)
    section_font = pick_font(24)
    body_font = pick_font(28)
    summary_font = pick_font(22)
    footer_font = pick_font(14)

    title = report["daily_quote"]
    draw.text((32, 28), title, fill="white", font=title_font)
    draw.text((32, 88), report["date_label"], fill="#dbeafe", font=date_font)

    y = header_height + 28
    draw.text((32, y), "中信期货 净持仓数据", fill="#1e293b", font=section_font)
    y += 48

    for symbol in SYMBOLS:
        net = report["citic_by_symbol"][symbol]
        line = f"{symbol}({SYMBOL_NAMES[symbol]}) {format_net_change(net)}"
        draw.text((40, y), line, fill="#0f172a", font=body_font)
        y += 52

    if chart_path and chart_path.exists():
        y += 12
        chart = Image.open(chart_path).convert("RGB")
        chart.thumbnail((width // 2 - 64, 420))
        image.paste(chart, (width // 2 + 16, header_height + 28))

    draw.line((32, y, width - 32, y), fill="#cbd5e1", width=2)
    y += 28

    summaries = [
        ("中信整体", format_overall(report["citic_total"])),
        ("前20机构净空单", f"{report['top20_net_short_total']:,}手"),
        ("今日净买入", f"{report['net_buy_total']:,}手"),
    ]
    card_width = (width - 88) // 3
    for index, (label, value) in enumerate(summaries):
        x = 32 + index * (card_width + 12)
        draw.rounded_rectangle(
            (x, y, x + card_width, y + 96),
            radius=14,
            fill="#eff6ff" if index == 0 else "#f1f5f9",
            outline="#93c5fd" if index == 0 else "#e2e8f0",
        )
        draw.text((x + 14, y + 14), label, fill="#64748b", font=summary_font)
        draw.text((x + 14, y + 48), value, fill="#1d4ed8" if index == 0 else "#0f172a", font=summary_font)

    footer_y = height - 72
    draw.line((32, footer_y - 16, width - 32, footer_y - 16), fill="#e2e8f0", width=1)
    for index, line in enumerate(DISCLAIMER_LINES):
        bbox = draw.textbbox((0, 0), line, font=footer_font)
        text_width = bbox[2] - bbox[0]
        draw.text(((width - text_width) / 2, footer_y + index * 22), line, fill="#94a3b8", font=footer_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def render_image(report: dict, config: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chart_url = fetch_chart_url(report, config)
    chart_path = output_path.parent / "chart.png"
    if chart_url:
        download_chart_image(chart_url, chart_path)
    else:
        chart_path = None

    html = build_html(report, config, chart_url, output_path.parent)
    if render_with_playwright(html, output_path):
        return
    render_fallback_image(report, config, output_path, chart_path)


def write_json(report: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


DEFAULT_DOUYIN_TAGS = ["期货", "股指期货", "中信期货", "持仓数据", "金融"]


def format_signed_value(value: int) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value}"


def build_douyin_title(trade_date: date) -> str:
    title = f"{trade_date.strftime('%Y%m%d')}中信期货净持仓"
    return title[:30]


def build_douyin_description(report: dict) -> str:
    symbols_line = "  ".join(
        f"{symbol} {format_signed_value(report['citic_by_symbol'][symbol])}"
        for symbol in SYMBOLS
    )
    total = report["citic_total"]
    if total >= 0:
        total_line = f"中信合计净多 {format_signed_value(total)}"
    else:
        total_line = f"中信合计净空 {abs(total)}"

    return "\n".join(
        [
            f"{report['date_label']} 中信期货净持仓数据",
            "",
            symbols_line,
            total_line,
            f"Top20净空 {report['top20_net_short_total']}  净买入 {report['net_buy_total']}",
            "",
            report["daily_quote"],
        ]
    )


def build_douyin_video_config(report: dict, mp4_name: str, config: dict) -> dict:
    trade_date = datetime.strptime(report["trade_date"], "%Y%m%d").date()
    douyin_cfg = config.get("douyin", {})
    tags = douyin_cfg.get("tags", DEFAULT_DOUYIN_TAGS)
    return {
        "videoPath": mp4_name,
        "title": build_douyin_title(trade_date),
        "description": build_douyin_description(report),
        "tags": list(tags)[:5],
    }


def write_douyin_configs(report: dict, output_dir: Path, stem: str, config: dict) -> tuple[Path, Path]:
    mp4_name = f"citic-net-positions-{stem}.mp4"
    douyin_config = build_douyin_video_config(report, mp4_name, config)
    dated_path = output_dir / f"citic-net-positions-{stem}-douyin.json"
    latest_path = output_dir / "douyin-video.json"
    write_json(douyin_config, dated_path)
    write_json(douyin_config, latest_path)
    return dated_path, latest_path


def render_video(json_path: Path, mp4_path: Path) -> None:
    import subprocess

    script = SCRIPT_DIR / "render_video.mjs"
    rel_json = json_path.relative_to(ROOT)
    rel_mp4 = mp4_path.relative_to(ROOT)
    try:
        subprocess.run(
            ["node", str(script), "--json", str(rel_json), "--output", str(rel_mp4)],
            cwd=ROOT,
            check=True,
            timeout=300,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"Video render skipped: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Trade date in YYYYMMDD format. Defaults to today.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--force", action="store_true", help="Run even on weekends.")
    args = parser.parse_args()

    config = load_config(args.config)
    output_dir = Path(args.output_dir or config.get("output_dir", DEFAULT_OUTPUT))
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    trade_date = resolve_trade_date(args.date)

    if is_weekend(trade_date) and not args.force:
        print(f"Skip {trade_date:%Y-%m-%d}: weekend.")
        return 0

    try:
        report = fetch_report(trade_date)
        report["logo_handle"] = config.get("logo_handle", DEFAULT_LOGO_HANDLE)
        bgm_cfg = config.get("bgm", {})
        report["bgm_enabled"] = bool(bgm_cfg.get("enabled", True) and BGM_FILE.exists())
        report["bgm_volume"] = float(bgm_cfg.get("volume", 0.12))
    except urllib.error.HTTPError as exc:
        print(f"No CFFEX data for {trade_date:%Y%m%d} ({exc.code}). Likely a non-trading day.")
        return 0
    except urllib.error.URLError as exc:
        print(f"Failed to fetch CFFEX data: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    stem = trade_date.strftime("%Y%m%d")
    png_path = output_dir / f"citic-net-positions-{stem}.png"
    json_path = output_dir / f"citic-net-positions-{stem}.json"

    render_image(report, config, png_path)
    write_json(report, json_path)

    mp4_path = output_dir / f"citic-net-positions-{stem}.mp4"
    render_video(json_path, mp4_path)

    douyin_dated_path, douyin_latest_path = write_douyin_configs(report, output_dir, stem, config)

    print(f"Saved image: {png_path}")
    print(f"Saved video: {mp4_path}")
    print(f"Saved data:  {json_path}")
    print(f"Saved douyin config: {douyin_dated_path}")
    print(f"Saved douyin config: {douyin_latest_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
