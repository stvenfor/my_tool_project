#!/usr/bin/env python3
"""From a reference video: extract music, fetch online clips, beat-sync montage."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reference video -> online clips -> beat-sync montage.")
    parser.add_argument(
        "--reference",
        default=str(ROOT / "work" / "output" / "hongri-montage.mp4"),
        help="Reference video (audio + timing extracted from this)",
    )
    parser.add_argument("--max-duration", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse clips already in clips/")
    parser.add_argument("--source", choices=["douyin", "mixkit", "web"], default="web", help="Clip source library")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument(
        "--sync-mode",
        choices=["auto", "reference", "beat", "beat_replace"],
        default="auto",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Search Douyin URLs by beat section keywords, then download and montage",
    )
    parser.add_argument("--skip-discover", action="store_true", help="Skip keyword search; reuse urls in douyin_sources.json")
    parser.add_argument("--force-fetch", action="store_true", help="Re-download and re-slice Douyin clips")
    parser.add_argument("--min-downloads", type=int, default=8, help="Minimum unique Douyin videos to download")
    parser.add_argument("--output", default="", help="Final rendered MP4 path (default: <reference-stem>-web-montage.mp4)")
    return parser.parse_args()


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def extract_audio(reference: Path, audio_out: Path) -> None:
    audio_out.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(reference),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            str(audio_out),
        ]
    )


def _load_manifest(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _resolve_sync_mode(
    source: str,
    sync_mode: str,
    manifest: list[dict],
    reference: Path | None = None,
) -> str:
    if sync_mode != "auto":
        return sync_mode

    source_videos = {clip.get("source_video") for clip in manifest if clip.get("source_video")}
    if source == "douyin" and len(source_videos) == 1 and reference is not None:
        ref = str(reference.resolve())
        if all(str(Path(item).resolve()) == ref for item in source_videos):
            return "reference"
    if source == "douyin":
        return "beat_replace"
    return "beat"


def main() -> None:
    args = parse_args()
    reference = Path(args.reference).resolve()
    if not reference.exists():
        raise SystemExit(f"Reference video not found: {reference}")

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    output_dir = ROOT / "output"
    render_output_dir = ROOT / "work" / "output" if config.get("output_dir", "_beat-montage/output") in ("_beat-montage/output", "modules/beat-montage/work/output") else PROJECT_ROOT / config.get("output_dir", "_beat-montage/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    render_output_dir.mkdir(parents=True, exist_ok=True)

    stem = reference.stem
    audio_path = ROOT / "bgm" / f"{stem}-ref.mp3"
    audio_rel = f"bgm/{audio_path.name}"
    extract_audio(reference, audio_path)

    ref_cuts_path = output_dir / f"reference_cuts.{stem}.json"
    run(
        [
            sys.executable,
            str(ROOT / "extract_reference_cuts.py"),
            str(reference),
            "--output",
            str(ref_cuts_path),
            "--max-duration",
            str(args.max_duration),
        ]
    )

    beats_path = output_dir / f"beats.{stem}.json"
    run(
        [
            sys.executable,
            str(ROOT / "analyze_beats.py"),
            str(audio_path),
            "--output",
            str(beats_path),
            "--max-duration",
            str(args.max_duration),
        ]
    )

    cut_grid_path = output_dir / f"cut_grid.{stem}.json"
    run(
        [
            sys.executable,
            str(ROOT / "merge_cut_grid.py"),
            "--beats",
            str(beats_path),
            "--reference-cuts",
            str(ref_cuts_path),
            "--output",
            str(cut_grid_path),
        ]
    )

    discovery_path = output_dir / f"discovered_urls.{stem}.json"
    manifest_path = ROOT / "clip_manifest.json"

    if not args.skip_fetch:
        if args.source == "douyin":
            if args.discover and not args.skip_discover:
                run(
                    [
                        sys.executable,
                        str(ROOT / "search_douyin_clips.py"),
                        "--beats",
                        str(beats_path),
                        "--seeds-only",
                        "--min-urls",
                        "12",
                    ]
                )
            fetch_cmd = [
                sys.executable,
                str(ROOT / "fetch_douyin_clips.py"),
                "--cut-grid",
                str(cut_grid_path),
                "--min-downloads",
                str(args.min_downloads),
            ]
            if discovery_path.exists():
                fetch_cmd.extend(["--from-discovery", str(discovery_path)])
            if args.force_fetch:
                fetch_cmd.append("--force")
            run(fetch_cmd)
        elif args.source == "web":
            run([sys.executable, str(ROOT / "fetch_web_clips.py"), "--try-douyin"])
        else:
            run([sys.executable, str(ROOT / "fetch_online_clips.py")])

    manifest = _load_manifest(manifest_path)
    sync_mode = _resolve_sync_mode(args.source, args.sync_mode, manifest, reference)
    print(f"Using sync mode: {sync_mode}")

    montage_path = output_dir / f"montage.{stem}.web.json"
    map_cmd = [
        sys.executable,
        str(ROOT / "map_clips.py"),
        "--beats",
        str(beats_path),
        "--audio",
        audio_rel,
        "--manifest",
        str(manifest_path),
        "--output",
        str(montage_path),
        "--edit-plan",
        str(output_dir / f"edit-plan.{stem}.web.json"),
        "--seed",
        str(args.seed),
        "--sync-mode",
        sync_mode,
        "--action-sync",
        "--cut-grid",
        str(cut_grid_path),
        "--finalize",
    ]
    run(map_cmd)

    if args.skip_render:
        print(f"Done (render skipped): {montage_path}")
        return

    if args.output:
        output_mp4 = Path(args.output).resolve()
    elif args.source == "douyin" and sync_mode in {"beat", "beat_replace"}:
        output_mp4 = render_output_dir / "7668-douyin-beat-mix.mp4"
        if not stem.startswith("7668"):
            output_mp4 = render_output_dir / f"{stem}-douyin-beat-mix.mp4"
    else:
        output_mp4 = render_output_dir / f"{stem}-web-mix.mp4"

    run(
        [
            "node",
            str(ROOT / "render.mjs"),
            "--montage",
            str(montage_path),
            "--output",
            str(output_mp4),
        ]
    )

    douyin_config = {
        "videoPath": str(output_mp4.relative_to(PROJECT_ROOT)),
        "title": config["douyin"]["title"],
        "description": config["douyin"]["description"] + " #抖音切片 #动作卡点",
        "tags": config["douyin"]["tags"] + ["抖音切片", "动作卡点"],
    }
    douyin_path = render_output_dir / f"douyin-{stem}-web-video.json"
    douyin_path.write_text(json.dumps(douyin_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output_mp4}")
    print(f"Saved douyin config: {douyin_path}")


if __name__ == "__main__":
    main()
