#!/usr/bin/env python3
"""Search Douyin share links by section keywords for beat-sync montage."""

from __future__ import annotations

import argparse
import json
import re
import socket
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_KEYWORDS = ROOT / "douyin_search_keywords.json"
DEFAULT_SOURCES = ROOT / "douyin_sources.json"
WEB_SOURCES = ROOT / "web_clips_sources.json"
DOUYIN_URL_RE = re.compile(r"https?://v\.douyin\.com/[A-Za-z0-9_\-]+/?")
SEARCH_TIMEOUT = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Douyin URLs by beat section keywords.")
    parser.add_argument("--beats", required=True, help="beats.{stem}.json from analyze_beats.py")
    parser.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES), help="Update urls in douyin_sources.json")
    parser.add_argument("--output", default="", help="discovered_urls.{stem}.json (default: output/discovered_urls.<stem>.json)")
    parser.add_argument("--review", action="store_true", help="Print discovered URLs and wait for Enter")
    parser.add_argument("--min-urls", type=int, default=12, help="Minimum unique URLs required")
    parser.add_argument("--seeds-only", action="store_true", help="Skip web search; fill from seed_urls only")
    parser.add_argument("--max-searches", type=int, default=4, help="Max keyword web searches")
    return parser.parse_args()


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract_links(html: str, max_results: int) -> list[str]:
    found: list[str] = []
    for match in DOUYIN_URL_RE.finditer(html):
        link = match.group(0).rstrip("/") + "/"
        if link not in found:
            found.append(link)
        if len(found) >= max_results:
            break
    return found


def _search_duckduckgo(query: str, max_results: int = 8) -> list[str]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        return _extract_links(_fetch_html(url), max_results)
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
        print(f"Search failed for '{query}': {exc}")
        return []


def _search_bing(query: str, max_results: int = 8) -> list[str]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    try:
        return _extract_links(_fetch_html(url), max_results)
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
        print(f"Bing search failed for '{query}': {exc}")
        return []


def search_keyword(keyword: str, per_keyword: int = 4) -> list[str]:
    query = f"site:v.douyin.com {keyword}"
    urls = _search_duckduckgo(query, per_keyword)
    if len(urls) < per_keyword:
        time.sleep(0.8)
        for link in _search_bing(query, per_keyword):
            if link not in urls:
                urls.append(link)
            if len(urls) >= per_keyword:
                break
    return urls


def _load_seed_urls(keyword_config: dict) -> list[str]:
    seeds: list[str] = list(keyword_config.get("seed_urls", []))
    if WEB_SOURCES.exists():
        web = _load_json(WEB_SOURCES)
        if isinstance(web, dict):
            for url in web.get("douyin_urls", []):
                if url not in seeds:
                    seeds.append(url)
    return seeds


def discover_urls(beats_data: dict, keyword_config: dict, max_searches: int = 4) -> dict:
    sections: list[dict] = beats_data.get("sections", [])
    section_names = [section["name"] for section in sections]
    discovered: dict[str, list[dict]] = {}
    all_urls: list[str] = []
    seed_urls = _load_seed_urls(keyword_config)
    seed_index = 0
    searches_done = 0

    for section_name in section_names:
        config = keyword_config.get(section_name)
        if not config:
            continue

        target = int(config.get("target_count", 2))
        keywords: list[str] = config.get("keywords", [])
        section_urls: list[dict] = []

        for keyword in keywords:
            if len(section_urls) >= target or searches_done >= max_searches:
                break
            print(f"Searching [{section_name}]: {keyword}")
            links = search_keyword(keyword, per_keyword=max(2, target))
            searches_done += 1
            for link in links:
                if link in all_urls:
                    continue
                all_urls.append(link)
                section_urls.append({"url": link, "keyword": keyword, "section": section_name})
                if len(section_urls) >= target:
                    break
            time.sleep(0.5)

        while len(section_urls) < target and seed_index < len(seed_urls):
            link = seed_urls[seed_index]
            seed_index += 1
            if link in all_urls:
                continue
            all_urls.append(link)
            section_urls.append({"url": link, "keyword": "seed", "section": section_name})

        discovered[section_name] = section_urls
        print(f"  -> {len(section_urls)} URLs for {section_name}")

    return {"sections": discovered, "urls": all_urls, "count": len(all_urls)}


def main() -> None:
    args = parse_args()
    beats_path = Path(args.beats).resolve()
    if not beats_path.exists():
        raise SystemExit(f"Beats file not found: {beats_path}")

    beats_data = _load_json(beats_path)
    keyword_config = _load_json(Path(args.keywords).resolve())
    stem = beats_path.stem.replace("beats.", "", 1) if beats_path.stem.startswith("beats.") else beats_path.stem

    output_path = Path(args.output).resolve() if args.output else ROOT / "output" / f"discovered_urls.{stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = discover_urls(
        beats_data,
        keyword_config,
        max_searches=0 if args.seeds_only else args.max_searches,
    )
    result["beats"] = str(beats_path)
    result["stem"] = stem

    if result["count"] < args.min_urls:
        print(
            f"Warning: only {result['count']} URLs found (min {args.min_urls}). "
            "Add more keywords or URLs manually to douyin_sources.json.",
            flush=True,
        )

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved discovery: {output_path} ({result['count']} URLs)")

    sources_path = Path(args.sources).resolve()
    sources = _load_json(sources_path) if sources_path.exists() else {"source": "douyin", "local_videos": [], "urls": []}
    sources["urls"] = result["urls"]
    sources["cookies_from_browser"] = sources.get("cookies_from_browser") or "chrome"
    sources["local_videos"] = []
    sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated sources: {sources_path}")

    if args.review:
        print("\nDiscovered URLs:")
        for url in result["urls"]:
            print(f"  {url}")
        input("Press Enter to continue...")


if __name__ == "__main__":
    main()
