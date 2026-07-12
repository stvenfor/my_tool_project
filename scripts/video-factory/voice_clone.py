#!/usr/bin/env python3
"""Optional ZipVoice clone wrapper for video-factory narration mode."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEALING_ROOT = ROOT.parent / "city-healing-video"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HEALING_ROOT))

from lib import load_json, resolve_work_dir, save_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone voice for narration via ZipVoice.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    work_dir = resolve_work_dir(config_path)

    ref_audio = config.get("voice_reference_audio")
    if not ref_audio:
        assets_ref = ROOT.parent.parent / "_video-factory" / "assets" / "voice" / "reference.wav"
        ref_audio = str(assets_ref) if assets_ref.exists() else ""
    ref_path = Path(str(ref_audio))
    if not ref_path.is_absolute():
        ref_path = ROOT.parent.parent / ref_path
    if not ref_path.exists():
        print("No voice reference found, falling back to edge-tts")
        from modes.common import run_cognitive_script  # noqa: E402
        import subprocess

        cognitive = ROOT.parent / "cognitive-video"
        subprocess.run(
            [sys.executable, str(cognitive / "synthesize_voice.py"), "--config", str(config_path)],
            check=True,
        )
        return

    script = load_json(work_dir / "script.json")
    narration = "\n".join(
        str(s.get("narration", s.get("dialogue", ""))).strip()
        for s in script.get("segments", [])
        if str(s.get("narration", s.get("dialogue", ""))).strip()
    )
    if not narration:
        raise SystemExit("No narration text in script.json")

    from zipvoice_clone import prepare_short_prompt, synthesize_zipvoice  # noqa: E402

    prompt_wav = work_dir / "voice_prompt.wav"
    prepare_short_prompt(ref_path, prompt_wav)
    output_wav = work_dir / "narration.wav"
    prompt_text = str(config.get("voice_reference_text", narration[:80]))
    synthesize_zipvoice(narration, prompt_wav, prompt_text, output_wav)
    print(f"Cloned voice: {output_wav}")


if __name__ == "__main__":
    main()
