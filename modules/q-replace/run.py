#!/usr/bin/env python3
"""Q-version character replacement pipeline entrypoint."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use HF mirror in CN if not set (speeds up first-time model download).
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from lib.common import load_config  # noqa: E402
from stages.assemble import run_assemble  # noqa: E402
from stages.composite import run_composite  # noqa: E402
from stages.identity import run_identity_generation  # noqa: E402
from stages.motion import run_motion_capture  # noqa: E402
from stages.probe import run_probe_and_extract  # noqa: E402
from stages.synthesize import run_synthesis  # noqa: E402
from stages.track import run_tracking  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace video characters with stylized or realistic characters.")
    parser.add_argument("video", help="Input video path")
    parser.add_argument(
        "--profile",
        choices=["default", "realistic"],
        default="",
        help="Preset config profile (overrides --config when set)",
    )
    parser.add_argument("--config", default="", help="Config YAML path")
    parser.add_argument("--output-dir", default="", help="Work/output directory")
    parser.add_argument("--from-stage", default="probe", help="Resume from stage")
    parser.add_argument("--preview-only", action="store_true", help="Only render preview segment")
    parser.add_argument("--no-diffusion", action="store_true", help="Skip SDXL diffusion (fast fallback)")
    parser.add_argument("--frame-limit", type=int, default=0, help="Limit analysis frames for quick test")
    parser.add_argument("--character-ref", default="", help="Fixed Q-character PNG/JPG for all persons")
    parser.add_argument("--keyframe-interval", type=int, default=0, help="Override keyframe interval")
    parser.add_argument("--skip-wav2lip", action="store_true", help="Skip Wav2Lip mouth sync")
    return parser.parse_args()


STAGES = ["probe", "track", "motion", "identity", "synthesize", "composite", "assemble"]


def main() -> None:
    args = parse_args()
    video_path = Path(args.video).resolve()
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")

    if args.profile == "realistic":
        config_path = ROOT / "config.realistic.yaml"
    elif args.config:
        config_path = Path(args.config)
    else:
        config_path = ROOT / "config.yaml"
    config = load_config(config_path)
    work_dir = Path(args.output_dir).resolve() if args.output_dir else ROOT / "output" / video_path.stem
    work_dir.mkdir(parents=True, exist_ok=True)

    frame_limit = args.frame_limit if args.frame_limit > 0 else None
    use_diffusion = not args.no_diffusion
    character_ref = Path(args.character_ref).resolve() if args.character_ref else None
    if character_ref and not character_ref.exists():
        raise SystemExit(f"Character reference not found: {character_ref}")
    keyframe_interval = args.keyframe_interval if args.keyframe_interval > 0 else None
    start_idx = STAGES.index(args.from_stage) if args.from_stage in STAGES else 0

    probe_manifest = None
    tracks_manifest = None
    motion_manifest = None
    identity_manifest = None
    synth_manifest = None
    composite_manifest = None

    if start_idx <= 0:
        print("[1/7] Probe + extract frames")
        probe_manifest = run_probe_and_extract(video_path, work_dir, config)
    else:
        from lib.common import load_json

        probe_manifest = load_json(work_dir / "probe.json")

    if start_idx <= 1:
        print("[2/7] Track persons + masks")
        tracks_manifest = run_tracking(probe_manifest, work_dir, config)
    else:
        from lib.common import load_json

        tracks_manifest = load_json(work_dir / "tracks.json")

    if start_idx <= 2:
        print("[3/7] Capture pose/face motion")
        motion_manifest = run_motion_capture(probe_manifest, tracks_manifest, work_dir, config)
    else:
        from lib.common import load_json

        motion_manifest = load_json(work_dir / "motion_manifest.json")

    if start_idx <= 3:
        print("[4/7] Generate character identities")
        identity_manifest = run_identity_generation(
            probe_manifest,
            tracks_manifest,
            motion_manifest,
            work_dir,
            config,
            use_diffusion=use_diffusion and character_ref is None,
            character_ref=character_ref,
        )
    else:
        from lib.common import load_json

        identity_manifest = load_json(work_dir / "identity_manifest.json")

    if start_idx <= 4:
        print("[5/7] Synthesize pose-driven character frames")
        synth_manifest = run_synthesis(
            probe_manifest,
            tracks_manifest,
            motion_manifest,
            identity_manifest,
            work_dir,
            config,
            use_diffusion=use_diffusion,
            frame_limit=frame_limit,
            video_path=video_path,
            skip_wav2lip=args.skip_wav2lip,
            keyframe_interval=keyframe_interval,
        )
    else:
        from lib.common import load_json

        synth_manifest = load_json(work_dir / "synth_manifest.json")

    if start_idx <= 5:
        print("[6/7] Composite on original background")
        composite_manifest = run_composite(
            probe_manifest,
            tracks_manifest,
            synth_manifest,
            work_dir,
            config,
            frame_limit=frame_limit,
        )
    else:
        from lib.common import load_json

        composite_manifest = load_json(work_dir / "composite_manifest.json")

    if start_idx <= 6:
        print("[7/7] Assemble output video")
        assemble_manifest = run_assemble(
            probe_manifest,
            composite_manifest,
            work_dir,
            video_path,
            config,
            preview_only=args.preview_only,
        )
    else:
        from lib.common import load_json

        assemble_manifest = load_json(work_dir / "assemble_manifest.json")

    print("\nDone.")
    print(f"Work dir: {work_dir}")
    if "preview_path" in assemble_manifest:
        print(f"Preview: {assemble_manifest['preview_path']}")
    if "final_path" in assemble_manifest:
        print(f"Final: {assemble_manifest['final_path']}")
        deliverable = video_path.parent / f"{video_path.stem}-q.mp4"
        shutil.copy2(assemble_manifest["final_path"], deliverable)
        print(f"Deliverable: {deliverable}")


if __name__ == "__main__":
    main()
