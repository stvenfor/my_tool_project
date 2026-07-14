"""Shared helpers for cognitive-video pipeline."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "work"
DOUYIN_DOWNLOADER = PROJECT_ROOT / "modules" / "shared" / "douyin" / "download_douyin_ref.mjs"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "topic"


def resolve_work_dir(config_path: Path) -> Path:
    return config_path.parent


def resolve_topic_dir(topic_id: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / slugify(topic_id)


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


def fit_audio_duration(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    sample_rate: int = 44100,
) -> float:
    current = get_audio_duration(input_wav)
    if current <= 0:
        raise RuntimeError(f"Invalid audio duration: {input_wav}")
    ratio = current / target_sec
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
    return get_audio_duration(output_wav)


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True)


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

    video_id = re.search(r"/video/(\d+)", url)
    direct_url = f"https://www.douyin.com/video/{video_id.group(1)}" if video_id else url
    for cookies in ("chrome", "safari", ""):
        cmd = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", str(output_mp4), direct_url]
        if cookies:
            cmd[1:1] = ["--cookies-from-browser", cookies]
        result = run_cmd(cmd)
        if result.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 10000:
            return
        print(result.stderr or result.stdout)

    raise SystemExit(
        f"Failed to download reference video. Place source manually at: {output_mp4}"
    )


def extract_audio_from_video(video_path: Path, output_audio: Path) -> None:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "aac",
            str(output_audio),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg audio extract failed")


def audio_to_wav(input_audio: Path, output_wav: Path, sample_rate: int = 44100) -> None:
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


def default_chinese_voice(config: dict[str, Any]) -> str:
    return str(config.get("voice", "zh-CN-YunjianNeural"))


def default_chinese_rate(config: dict[str, Any]) -> str:
    return str(config.get("voice_rate", "+14%"))


def default_chinese_pitch(config: dict[str, Any]) -> str:
    return str(config.get("voice_pitch", "-6Hz"))


def default_chinese_volume(config: dict[str, Any]) -> str:
    return str(config.get("voice_volume", "+5%"))


DEFAULT_SEGMENT_GAP_BY_PHASE: dict[str, float] = {
    "pain": 0.48,
    "insight": 0.40,
    "contrast": 0.34,
    "action": 0.28,
    "cta": 0.22,
}


def voice_rhythm_config(config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "strong_clause_gap_ms": 320,
        "comma_clause_gap_ms": 150,
        "clause_gap_ms": 220,
        "pitch_bounce_hz": 3,
        "rate_bounce_pct": 2,
        "opening_rate_drop_pct": 4,
        "closing_rate_boost_pct": 4,
        "prosody_by_phase": {
            "pain": {"rate_delta": -5, "pitch_delta": -1},
            "insight": {"rate_delta": -2, "pitch_delta": 0},
            "contrast": {"rate_delta": 0, "pitch_delta": 1},
            "action": {"rate_delta": 2, "pitch_delta": 1},
            "cta": {"rate_delta": 4, "pitch_delta": 2},
        },
    }
    custom = config.get("voice_rhythm") or {}
    merged = {**defaults, **custom}
    merged["segment_gap_by_phase"] = {
        **DEFAULT_SEGMENT_GAP_BY_PHASE,
        **(custom.get("segment_gap_by_phase") or {}),
    }
    return merged


def segment_gap_for_phase(config: dict[str, Any], phase: str) -> float:
    rhythm = voice_rhythm_config(config)
    by_phase = rhythm["segment_gap_by_phase"]
    fallback = float(config.get("narration_gap_sec", 0.32))
    return float(by_phase.get(phase, fallback))


def split_chinese_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；\n])|(?<=[!?;]\s)", text)
    chunks = [p.strip() for p in parts if p.strip()]
    if not chunks:
        chunks = [line.strip() for line in text.splitlines() if line.strip()]
    return chunks


PHASE_KEYWORDS: dict[str, list[str]] = {
    "pain": ["焦虑", "困", "博弈", "耗材", "不敢", "围城", "累", "压力"],
    "insight": ["认知", "赢家", "低欲", "退场", "刷新", "真相", "本质"],
    "contrast": ["当局", "局外", "对比", "反而", "其实", "不是", "而是"],
    "action": ["建议", "选择", "活法", "行动", "试试", "可以", "去换"],
    "cta": ["收藏", "关注", "点赞", "分享"],
}


def infer_phase(text: str, index: int, total: int) -> str:
    for phase, keywords in PHASE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return phase
    if index == 0:
        return "pain"
    if index >= total - 1:
        return "cta"
    if index == 1:
        return "insight"
    if index == total - 2:
        return "action"
    return "contrast"


def extract_emphasis(text: str, max_items: int = 3) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"[\u4e00-\u9fff]{2,8}", text):
        token = match.group(0)
        if token in {"我们", "你们", "他们", "这个", "那个", "一个", "不是", "而是", "其实", "但是"}:
            continue
        if token not in candidates:
            candidates.append(token)
    if len(candidates) < 2:
        chunks = re.split(r"[，,、\s]+", text)
        for chunk in chunks:
            chunk = chunk.strip("。！？；")
            if 2 <= len(chunk) <= 8 and chunk not in candidates:
                candidates.append(chunk)
    return candidates[:max_items]


VISUAL_KEYWORDS_BY_PHASE = {
    "pain": "都市白领 加班 地铁 焦虑",
    "insight": "城市夜景 思考 独处",
    "contrast": "对比 城市 小城 生活",
    "action": "慢生活 自然 日常 小城",
    "cta": "日落 风景 宁静",
}


def visual_keyword_for_phase(phase: str) -> str:
    return VISUAL_KEYWORDS_BY_PHASE.get(phase, "城市生活 风景")


PHILOSOPHY_BY_PHASE: dict[str, str] = {
    "pain": "别做耗材",
    "insight": "低欲即赢",
    "contrast": "欲望是牢",
    "action": "日子为本",
    "cta": "收藏智慧",
}


def truncate_zh(text: str, max_len: int = 8) -> str:
    cleaned = re.sub(r"\s+", "", text.strip())
    return cleaned[:max_len]


def philosophy_quote_for_segment(
    seg: dict[str, Any],
    config: dict[str, Any],
    max_len: int = 8,
) -> str:
    emphasis = seg.get("emphasis") or []
    for item in emphasis:
        quote = truncate_zh(str(item), max_len)
        if 2 <= len(quote) <= max_len:
            return quote
    phase = str(seg.get("phase", "insight"))
    fallback = str(config.get("philosophy_quote") or PHILOSOPHY_BY_PHASE.get(phase, "人间清醒"))
    return truncate_zh(fallback, max_len)
