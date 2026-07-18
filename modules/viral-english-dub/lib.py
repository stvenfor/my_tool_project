"""Shared helpers for viral-english-dub pipeline."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "work"
# CITY_HEALING_ROOT removed — zipvoice is local
DOUYIN_DOWNLOADER = PROJECT_ROOT / "modules" / "shared" / "douyin" / "download_douyin_ref.mjs"


def load_dotenv(dotenv_path: Path | None = None) -> None:
    """Load KEY=VALUE lines into os.environ if not already set."""
    import os

    path = dotenv_path or (PROJECT_ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "clip"


def resolve_work_dir(config_path: Path) -> Path:
    return config_path.parent


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True)


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    return float(result.stdout.strip())


def probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    fps_raw = str(stream.get("r_frame_rate", "30/1"))
    if "/" in fps_raw:
        num, den = fps_raw.split("/", 1)
        fps = float(num) / float(den or 1)
    else:
        fps = float(fps_raw)
    return {
        "width": int(stream.get("width", 1080)),
        "height": int(stream.get("height", 1920)),
        "fps": round(fps, 3),
        "duration_sec": round(float(fmt.get("duration", 0)), 3),
    }


def _atempo_chain(ratio: float) -> str:
    filters: list[str] = []
    remaining = ratio
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)


def trim_trailing_silence(
    input_wav: Path,
    output_wav: Path,
    *,
    sample_rate: int = 44100,
    stop_db: float = -45.0,
    min_silence_sec: float = 0.25,
) -> float:
    """Drop trailing silence only — never cut speech mid-word."""
    # stop_periods=-1 removes silence from the end only (positive values truncate at first pause).
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            (
                f"silenceremove=start_periods=0:stop_periods=-1:"
                f"stop_duration={min_silence_sec:.3f}:stop_threshold={stop_db}dB"
            ),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not output_wav.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_wav),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                str(output_wav),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    trimmed = get_audio_duration(output_wav)
    original = get_audio_duration(input_wav)
    # Guardrail: if “trim” ate speech, keep original.
    if trimmed < max(0.12, original * 0.55):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_wav),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                str(output_wav),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return get_audio_duration(output_wav)
    return trimmed


def fit_audio_duration(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    sample_rate: int = 44100,
    max_stretch_ratio: float = 1.15,
    *,
    exact: bool = False,
) -> float:
    current = get_audio_duration(input_wav)
    if current <= 0:
        raise RuntimeError(f"Invalid audio duration: {input_wav}")
    ratio = current / max(0.05, target_sec)
    if not exact:
        if ratio > max_stretch_ratio:
            ratio = max_stretch_ratio
        elif ratio < 1 / max_stretch_ratio:
            ratio = 1 / max_stretch_ratio
    # Clamp to ffmpeg atempo practical range and chain.
    ratio = max(0.25, min(4.0, ratio))
    filter_chain = _atempo_chain(ratio)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            filter_chain,
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg atempo failed")
    fitted = get_audio_duration(output_wav)
    # Snap residual drift to exact slot length for A/V sync.
    if exact and abs(fitted - target_sec) > 0.04:
        tmp = output_wav.with_suffix(".snap.wav")
        if fitted > target_sec:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(output_wav),
                    "-t",
                    f"{target_sec:.3f}",
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    str(tmp),
                ],
                capture_output=True,
                text=True,
            )
        else:
            pad = max(0.0, target_sec - fitted)
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(output_wav),
                    "-af",
                    f"apad=pad_dur={pad:.3f}",
                    "-t",
                    f"{target_sec:.3f}",
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    str(tmp),
                ],
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg snap failed")
        tmp.replace(output_wav)
        fitted = get_audio_duration(output_wav)
    return fitted


def fit_audio_prefer_complete(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    *,
    sample_rate: int = 44100,
    max_stretch_ratio: float = 1.22,
    max_output_sec: float | None = None,
) -> float:
    """Keep the full English line. Mild tempo only — never hard-trim speech."""
    cleaned = output_wav.with_suffix(".clean.wav")
    current = trim_trailing_silence(input_wav, cleaned, sample_rate=sample_rate)
    if current <= 0:
        raise RuntimeError(f"Invalid audio duration: {input_wav}")

    ceiling = max_output_sec if max_output_sec is not None else current * 2
    # Soft-compress only when over Chinese slot AND over video remap ceiling.
    if current > ceiling * 1.02:
        desired = ceiling
        fitted = fit_audio_duration(
            cleaned,
            output_wav,
            desired,
            sample_rate=sample_rate,
            max_stretch_ratio=max(max_stretch_ratio, current / max(0.08, desired)),
            exact=False,
        )
    elif current > target_sec * 1.08 and current / target_sec <= max_stretch_ratio:
        fitted = fit_audio_duration(
            cleaned,
            output_wav,
            target_sec,
            sample_rate=sample_rate,
            max_stretch_ratio=max_stretch_ratio,
            exact=False,
        )
    else:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(cleaned),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                str(output_wav),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg copy failed")
        fitted = get_audio_duration(output_wav)

    if cleaned.exists() and cleaned != output_wav:
        cleaned.unlink(missing_ok=True)
    return fitted


def fit_audio_for_slot(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    sample_rate: int = 44100,
    max_stretch_ratio: float = 1.35,
) -> float:
    """Legacy exact-slot fit (can cut speech). Prefer fit_audio_prefer_complete."""
    return fit_audio_duration(
        input_wav,
        output_wav,
        target_sec,
        sample_rate=sample_rate,
        max_stretch_ratio=max_stretch_ratio,
        exact=True,
    )


def download_reference_video(url: str, output_mp4: Path) -> None:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if DOUYIN_DOWNLOADER.exists():
        result = run_cmd(
            ["node", str(DOUYIN_DOWNLOADER), "--url", url, "--output", str(output_mp4)],
            cwd=DOUYIN_DOWNLOADER.parent,
        )
        if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 10000:
            return
        print(result.stderr or result.stdout)
    raise SystemExit(f"Failed to download reference video. Place source manually at: {output_mp4}")


def copy_local_video(input_path: Path, output_mp4: Path) -> None:
    if not input_path.exists():
        raise SystemExit(f"Input video not found: {input_path}")
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if input_path.resolve() == output_mp4.resolve():
        return
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-c", "copy", str(output_mp4)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        shutil_copy(input_path, output_mp4)


def shutil_copy(src: Path, dest: Path) -> None:
    import shutil

    shutil.copy2(src, dest)


def extract_audio_from_video(video_path: Path, output_audio: Path) -> None:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "aac", str(output_audio)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg audio extract failed")


def audio_to_wav(input_audio: Path, output_wav: Path, sample_rate: int = 16000) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_audio),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg wav convert failed")


def extract_audio_segment(
    source_wav: Path,
    output_wav: Path,
    start_sec: float,
    end_sec: float,
    sample_rate: int = 24000,
) -> None:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.05, end_sec - start_sec)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(source_wav),
            "-t",
            f"{duration:.3f}",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg segment extract failed")


def default_english_voice(config: dict[str, Any]) -> str:
    return str(config.get("voice", "en-US-GuyNeural"))


def default_english_rate(config: dict[str, Any]) -> str:
    return str(config.get("voice_rate", "-5%"))


def detect_torch_device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def speaker_prompt_path(work_dir: Path, speaker_id: str) -> Path:
    return work_dir / "reference" / f"speaker_{speaker_id}_prompt.wav"


def speaker_prompt_text_path(work_dir: Path, speaker_id: str) -> Path:
    return work_dir / "reference" / f"speaker_{speaker_id}_prompt.txt"


def resolve_target_video_path(
    config: dict[str, Any],
    *,
    input_path: Path | None = None,
    url: str = "",
) -> Path | None:
    if input_path and input_path.exists():
        return input_path.expanduser()
    if url:
        return None
    for key in ("target_input", "reference_input"):
        raw = config.get(key)
        if raw:
            path = Path(str(raw)).expanduser()
            if path.exists():
                return path
    return None


def resolve_voice_reference_path(config: dict[str, Any]) -> Path | None:
    raw = config.get("voice_reference_input") or config.get("voice_reference")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.exists() else None


def ensure_config(work_dir: Path, clip_id: str, overrides: dict[str, Any] | None = None) -> Path:
    config_path = work_dir / "config.json"
    if not config_path.exists():
        template = load_json(ROOT / "config.template.json")
        template["clip_id"] = clip_id
        if overrides:
            template.update(overrides)
        save_json(config_path, template)
    return config_path
