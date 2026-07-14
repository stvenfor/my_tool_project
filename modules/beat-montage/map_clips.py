#!/usr/bin/env python3
"""Map beat timeline to clip slots using EditPlan-style planning."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DURATION_TOLERANCE = 0.5
MIN_CLIP_DURATION = 0.25
MAX_CLIP_DURATION = 3.0

SECTION_RULES = {
    "cold": {"priority": ["comedy", "slow_build"], "beats_per_cut": 2.0, "fx": []},
    "warm": {"priority": ["slow_build", "action_punch"], "beats_per_cut": 1.33, "fx": ["zoom"]},
    "hot": {"priority": ["action_punch", "action_gun"], "beats_per_cut": 1.0, "fx": ["flash", "zoom"]},
    "outro": {"priority": ["hero_shot", "slow_build"], "beats_per_cut": 3.0, "fx": []},
}

SECTION_ENERGY: dict[str, tuple[int, int]] = {
    "cold": (1, 4),
    "warm": (4, 7),
    "hot": (7, 10),
    "outro": (3, 6),
}

SECTION_PEAK_TARGET: dict[str, float] = {
    "cold": 0.35,
    "warm": 0.55,
    "hot": 0.82,
    "outro": 0.45,
}

SECTION_RANK = {"cold": 0, "warm": 1, "hot": 2, "outro": 1}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate montage draft from beats and clip manifest.")
    parser.add_argument("--beats", default=str(ROOT / "output" / "beats.json"))
    parser.add_argument("--manifest", default=str(ROOT / "clip_manifest.json"))
    parser.add_argument("--audio", default="", help="Override audio path in montage output (prefer bgm/*.mp3)")
    parser.add_argument("--output", default=str(ROOT / "output" / "montage.draft.json"))
    parser.add_argument("--edit-plan", default="", help="Also write EditPlan JSON to this path")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--action-sync", action="store_true", default=True, help="Align clip action peaks to beats")
    parser.add_argument("--no-action-sync", dest="action_sync", action="store_false")
    parser.add_argument(
        "--sync-mode",
        choices=["auto", "reference", "beat", "beat_replace"],
        default="auto",
        help="reference=keep original slice timeline; beat=map to detected beats; beat_replace=cut_grid + multi-video",
    )
    parser.add_argument("--cut-grid", default="", help="cut_grid.{stem}.json for beat_replace mode")
    parser.add_argument("--finalize", action="store_true", help="Write montage.json instead of draft")
    return parser.parse_args()


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def format_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


def parse_mmss(value: str) -> float:
    minutes, secs = value.split(":")
    return int(minutes) * 60 + int(secs)


def validate_edit_plan(plan: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []

    audio_start = plan.get("audio_start", "0:00")
    if not isinstance(audio_start, str) or ":" not in audio_start:
        errors.append("audio_start must be MM:SS format")
    else:
        try:
            if parse_mmss(audio_start) < 0:
                errors.append("audio_start must be non-negative")
        except ValueError:
            errors.append("audio_start must be MM:SS format")

    audio_duration = plan.get("audio_duration", 0)
    if not isinstance(audio_duration, (int, float)) or audio_duration <= 0:
        errors.append("audio_duration must be positive")

    clips = plan.get("clips", [])
    if not clips:
        errors.append("clips must be non-empty")

    total_duration = 0.0
    for index, clip in enumerate(clips):
        video_start = clip.get("video_start")
        duration = clip.get("duration")
        if not isinstance(video_start, str) or ":" not in video_start:
            errors.append(f"clip[{index}].video_start must be MM:SS format")
        elif parse_mmss(video_start) < 0:
            errors.append(f"clip[{index}].video_start must be non-negative")
        if not isinstance(duration, (int, float)) or duration <= 0:
            errors.append(f"clip[{index}].duration must be positive")
        elif duration < MIN_CLIP_DURATION:
            errors.append(f"clip[{index}].duration < {MIN_CLIP_DURATION}s may look glitchy")
        elif duration > 30:
            errors.append(f"clip[{index}].duration > 30s may feel static")
        else:
            total_duration += float(duration)

    if isinstance(audio_duration, (int, float)) and audio_duration > 0:
        if abs(total_duration - float(audio_duration)) > DURATION_TOLERANCE:
            errors.append(
                f"clip durations sum to {total_duration:.3f}s, expected {float(audio_duration):.3f}s "
                f"(tolerance {DURATION_TOLERANCE}s)"
            )

    return len(errors) == 0, errors


def _group_by_type(manifest: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for clip in manifest:
        grouped.setdefault(clip["type"], []).append(clip)
    return grouped


def _section_for_time(sections: list[dict], t: float) -> str:
    for section in sections:
        if section["start"] <= t < section["end"]:
            return str(section["name"])
    return "outro"


def _next_section(sections: list[dict], t: float) -> str | None:
    for index, section in enumerate(sections):
        if section["start"] <= t < section["end"]:
            if index + 1 < len(sections):
                return str(sections[index + 1]["name"])
            return None
    return None


def _section_by_name(sections: list[dict], name: str) -> dict | None:
    for section in sections:
        if section["name"] == name:
            return section
    return None


def _is_pre_drop(sections: list[dict], start_time: float, section_name: str, next_section: str | None) -> bool:
    if not next_section or SECTION_RANK.get(next_section, 0) <= SECTION_RANK.get(section_name, 0):
        return False
    next_meta = _section_by_name(sections, next_section)
    if not next_meta:
        return False
    return start_time >= float(next_meta["start"]) - 0.8


def _beat_duration(beats: list[float], start_beat: int, duration_beats: int, audio_duration: float) -> float:
    end_beat = min(len(beats) - 1, start_beat + duration_beats)
    start_time = beats[start_beat]
    end_time = beats[end_beat] if end_beat > start_beat else audio_duration
    duration = max(MIN_CLIP_DURATION, end_time - start_time)
    return min(duration, MAX_CLIP_DURATION)


def _score_clip(
    clip: dict,
    section: str,
    rule: dict,
    recent_ids: list[str],
    recent_types: list[str],
    force_type: str | None,
) -> float:
    if force_type and clip["type"] != force_type:
        return -1.0

    energy_lo, energy_hi = SECTION_ENERGY.get(section, (4, 7))
    energy_target = (energy_lo + energy_hi) / 2
    energy_score = 1.0 - min(1.0, abs(float(clip.get("energy", 5)) - energy_target) / 5.0)

    type_score = 0.0
    for index, clip_type in enumerate(rule["priority"]):
        if clip["type"] == clip_type:
            type_score = 1.0 - index * 0.25
            break

    repeat_penalty = 0.0
    if clip["id"] in recent_ids[-3:]:
        repeat_penalty += 0.9
    if recent_types and recent_types[-1] == clip["type"]:
        repeat_penalty += 0.35
    if len(recent_types) >= 2 and recent_types[-1] == recent_types[-2] == clip["type"]:
        repeat_penalty += 0.5

    hint = float(clip.get("duration_hint", 1.5))
    hint_score = 1.0 - min(1.0, abs(hint - 1.0) / 2.0) * 0.2

    return energy_score * 0.45 + type_score * 0.35 + hint_score * 0.2 - repeat_penalty


def _pick_clip(
    grouped: dict[str, list[dict]],
    section: str,
    rule: dict,
    rng: random.Random,
    recent_ids: list[str],
    recent_types: list[str],
    force_type: str | None = None,
) -> dict:
    all_clips = [clip for group in grouped.values() for clip in group]
    scored = [
        (clip, _score_clip(clip, section, rule, recent_ids, recent_types, force_type))
        for clip in all_clips
    ]
    scored = [(clip, score) for clip, score in scored if score >= 0]
    if not scored:
        return rng.choice(all_clips)

    scored.sort(key=lambda item: item[1], reverse=True)
    top_score = scored[0][1]
    shortlist = [clip for clip, score in scored if score >= top_score - 0.15]
    return rng.choice(shortlist)


def _build_reasoning(sections: list[dict], cuts: list[dict]) -> str:
    section_counts: dict[str, int] = {}
    for cut in cuts:
        section_counts[cut["section"]] = section_counts.get(cut["section"], 0) + 1
    parts = [f"{name}={count}" for name, count in section_counts.items()]
    section_names = ", ".join(f"{s['name']}({s['start']:.1f}-{s['end']:.1f}s)" for s in sections)
    return f"Cold-to-hot arc across [{section_names}]; clip distribution: {', '.join(parts)}."


def _pick_action_trim(
    clip: dict,
    section: str,
    duration: float,
    used_peak_keys: dict[str, set[str]],
    rng: random.Random,
) -> tuple[float, str]:
    peaks: list[dict] = clip.get("action_peaks") or []
    if not peaks:
        trim = float(clip.get("trim_in", 0.0))
        return trim, "fallback-trim"

    clip_id = clip["id"]
    used = used_peak_keys.setdefault(clip_id, set())
    target = SECTION_PEAK_TARGET.get(section, 0.55)
    source_duration = float(clip.get("source_duration", 999.0))

    ranked = sorted(
        peaks,
        key=lambda peak: abs(float(peak.get("strength", 0.5)) - target) + rng.random() * 0.04,
    )

    chosen: dict | None = None
    for peak in ranked:
        key = f"{peak.get('time', 0):.3f}"
        if key in used:
            continue
        peak_time = float(peak["time"])
        if peak_time + duration > source_duration + 0.05:
            continue
        chosen = peak
        used.add(key)
        break

    if chosen is None:
        used.clear()
        chosen = ranked[0]
        used.add(f"{chosen.get('time', 0):.3f}")

    trim = max(0.0, float(chosen["time"]))
    strength = float(chosen.get("strength", 0.5))
    return trim, f"action-hit@{trim:.2f}s(s={strength:.2f})"


def _fx_for_cut(section: str, rule: dict, action_strength: float) -> list[str]:
    fx: list[str] = []
    if section == "hot" and action_strength >= 0.72 and "flash" in rule["fx"]:
        fx.append("flash")
    if section in {"warm", "hot"} and action_strength >= 0.45 and "zoom" in rule["fx"]:
        fx.append("zoom")
    return fx


def _can_reference_sync(manifest: list[dict]) -> bool:
    if not manifest:
        return False
    return all(isinstance(item.get("source_range"), list) and len(item["source_range"]) == 2 for item in manifest)


def build_edit_plan_reference(beats_data: dict, manifest: list[dict]) -> dict:
    """Place each slice at its original timestamp — preserves source montage music sync."""
    sections: list[dict] = beats_data["sections"]
    audio_duration = float(beats_data["duration"])
    clips_sorted = sorted(manifest, key=lambda item: float(item["source_range"][0]))

    edit_clips: list[dict] = []
    montage_cuts: list[dict] = []

    for index, clip in enumerate(clips_sorted):
        src_start, src_end = float(clip["source_range"][0]), float(clip["source_range"][1])
        if src_start >= audio_duration - 0.02:
            break

        duration = min(src_end, audio_duration) - src_start
        if duration < MIN_CLIP_DURATION:
            continue

        section_name = _section_for_time(sections, src_start)
        rule = SECTION_RULES[section_name]

        # Scene slice starts at the original cut point — trim from 0, not a random action peak.
        trim_in = 0.0
        peaks = clip.get("action_peaks") or []
        if peaks:
            first_peak = float(peaks[0]["time"])
            if first_peak <= 0.35:
                trim_in = max(0.0, first_peak - 0.03)

        action_strength = float(peaks[0]["strength"]) if peaks else 0.5
        tag = clip.get("tags", [clip["type"]])[0] if clip.get("tags") else clip["type"]
        description = f"{tag} [ref@{src_start:.2f}s]"

        edit_clip = {
            "video_start": format_mmss(trim_in),
            "duration": round(duration, 3),
            "description": description,
            "clip_id": clip["id"],
            "clip_path": f"clips/{clip['path']}",
            "section": section_name,
            "audio_start": format_mmss(src_start),
        }
        edit_clips.append(edit_clip)
        montage_cuts.append(
            {
                "clip": edit_clip["clip_path"],
                "clipId": clip["id"],
                "section": section_name,
                "startBeat": index,
                "startTime": round(src_start, 3),
                "durationBeats": 1,
                "duration": edit_clip["duration"],
                "trimIn": trim_in,
                "fx": _fx_for_cut(section_name, rule, action_strength),
                "description": description,
                "actionSync": f"reference@{src_start:.2f}s",
            }
        )

    _normalize_durations(edit_clips, montage_cuts, audio_duration)
    reasoning = (
        f"Reference timeline sync: {len(montage_cuts)} slices placed at original source timestamps "
        f"(0–{audio_duration:.1f}s). Preserves source montage beat alignment."
    )

    return {
        "audio_start": "0:00",
        "audio_duration": round(audio_duration, 3),
        "clips": edit_clips,
        "reasoning": reasoning,
        "montage_cuts": montage_cuts,
    }


def build_edit_plan_beat_replace(
    beats_data: dict,
    manifest: list[dict],
    cut_grid: dict,
    rng: random.Random,
    action_sync: bool = True,
) -> dict:
    """Map cut_grid slots to unique source videos with action peaks on beat."""
    sections: list[dict] = beats_data["sections"]
    audio_duration = float(beats_data["duration"])
    slots: list[dict] = cut_grid.get("slots", [])
    grouped = _group_by_type(manifest)
    used_source_videos: set[str] = set()
    used_clip_ids: set[str] = set()

    edit_clips: list[dict] = []
    montage_cuts: list[dict] = []

    for slot in slots:
        start_time = float(slot["startTime"])
        duration = float(slot["duration"])
        section_name = str(slot.get("section") or _section_for_time(sections, start_time))
        rule = SECTION_RULES[section_name]

        available = [
            clip
            for clip in manifest
            if clip["id"] not in used_clip_ids
            and str(clip.get("source_video", "")) not in used_source_videos
        ]
        if not available:
            available = [clip for clip in manifest if clip["id"] not in used_clip_ids]
        if not available:
            available = list(manifest)

        scored = [
            (clip, _score_clip(clip, section_name, rule, [], [], None))
            for clip in available
        ]
        scored = [(clip, score) for clip, score in scored if score >= 0]
        scored.sort(key=lambda item: item[1], reverse=True)
        if not scored:
            clip = rng.choice(manifest)
        else:
            top_score = scored[0][1]
            shortlist = [clip for clip, score in scored if score >= top_score - 0.12]
            clip = rng.choice(shortlist)

        trim_in = float(clip.get("trim_in", 0.0))
        sync_note = "static-trim"
        action_strength = 0.5
        if action_sync:
            peaks: list[dict] = clip.get("action_peaks") or []
            if peaks:
                target = SECTION_PEAK_TARGET.get(section_name, 0.55)
                chosen = min(
                    peaks,
                    key=lambda peak: abs(float(peak.get("strength", 0.5)) - target) + rng.random() * 0.03,
                )
                trim_in = max(0.0, float(chosen["time"]))
                action_strength = float(chosen.get("strength", 0.5))
                sync_note = f"action-hit@{trim_in:.2f}s(s={action_strength:.2f})"
            else:
                sync_note = "fallback-trim"

        ref_cut = slot.get("referenceCut")
        beat_snap = int(slot.get("beatSnapMs", 0))
        tag = clip.get("tags", [clip["type"]])[0] if clip.get("tags") else clip["type"]
        description = f"{tag} [{sync_note}]"

        edit_clip = {
            "video_start": format_mmss(trim_in),
            "duration": round(duration, 3),
            "description": description,
            "clip_id": clip["id"],
            "clip_path": f"clips/{clip['path']}",
            "section": section_name,
            "audio_start": format_mmss(start_time),
        }
        edit_clips.append(edit_clip)
        montage_cuts.append(
            {
                "clip": edit_clip["clip_path"],
                "clipId": clip["id"],
                "section": section_name,
                "startBeat": int(slot.get("index", len(montage_cuts))),
                "startTime": round(start_time, 3),
                "durationBeats": 1,
                "duration": edit_clip["duration"],
                "trimIn": trim_in,
                "fx": _fx_for_cut(section_name, rule, action_strength),
                "description": description,
                "actionSync": sync_note,
                "referenceCut": ref_cut,
                "beatSnapMs": beat_snap,
            }
        )

        used_clip_ids.add(clip["id"])
        source_video = str(clip.get("source_video", ""))
        if source_video:
            used_source_videos.add(source_video)

    _normalize_durations(edit_clips, montage_cuts, audio_duration)
    unique_sources = len({c.get("source_video") for c in manifest if c.get("clipId")})
    reasoning = (
        f"Beat-replace: {len(montage_cuts)} slots from cut_grid, "
        f"{len(used_source_videos)} unique source videos, beat-priority timeline."
    )
    if action_sync:
        reasoning += " Action peaks aligned to cut points."

    return {
        "audio_start": "0:00",
        "audio_duration": round(audio_duration, 3),
        "clips": edit_clips,
        "reasoning": reasoning,
        "montage_cuts": montage_cuts,
    }


def build_edit_plan(beats_data: dict, manifest: list[dict], rng: random.Random, action_sync: bool = True) -> dict:
    beats: list[float] = beats_data.get("cut_beats") or beats_data["beats"]
    sections: list[dict] = beats_data["sections"]
    audio_duration = float(beats_data["duration"])
    grouped = _group_by_type(manifest)

    clips: list[dict] = []
    montage_cuts: list[dict] = []
    recent_ids: list[str] = []
    recent_types: list[str] = []
    used_peak_keys: dict[str, set[str]] = {}

    beat_index = 0
    while beat_index < len(beats):
        start_beat = beat_index
        start_time = beats[start_beat]
        section_name = _section_for_time(sections, start_time)
        next_section = _next_section(sections, start_time)
        rule = SECTION_RULES[section_name]

        force_type: str | None = None
        if _is_pre_drop(sections, start_time, section_name, next_section):
            force_type = "slow_build"

        duration_beats = max(1, int(round(rule["beats_per_cut"])))
        if force_type:
            duration_beats = max(1, duration_beats - 1)

        end_beat = min(len(beats) - 1, start_beat + duration_beats)
        if end_beat <= start_beat and beat_index >= len(beats) - 1:
            break

        clip = _pick_clip(grouped, section_name, rule, rng, recent_ids, recent_types, force_type)
        duration = _beat_duration(beats, start_beat, duration_beats, audio_duration)

        sync_note = "static-trim"
        action_strength = 0.5
        if action_sync:
            trim_in, sync_note = _pick_action_trim(clip, section_name, duration, used_peak_keys, rng)
            for peak in clip.get("action_peaks") or []:
                if abs(float(peak.get("time", -1)) - trim_in) < 0.05:
                    action_strength = float(peak.get("strength", 0.5))
                    break
        else:
            trim_in = float(clip.get("trim_in", 0.0))

        description = clip.get("tags", [clip["type"]])[0] if clip.get("tags") else clip["type"]
        if force_type:
            description = f"蓄力→{next_section}: {description}"
        description = f"{description} [{sync_note}]"

        edit_clip = {
            "video_start": format_mmss(trim_in),
            "duration": round(duration, 3),
            "description": description,
            "clip_id": clip["id"],
            "clip_path": f"clips/{clip['path']}",
            "section": section_name,
            "audio_start": format_mmss(start_time),
        }
        clips.append(edit_clip)

        montage_cuts.append(
            {
                "clip": edit_clip["clip_path"],
                "clipId": clip["id"],
                "section": section_name,
                "startBeat": start_beat,
                "startTime": round(start_time, 3),
                "durationBeats": duration_beats,
                "duration": edit_clip["duration"],
                "trimIn": trim_in,
                "fx": _fx_for_cut(section_name, rule, action_strength),
                "description": description,
                "actionSync": sync_note,
            }
        )

        recent_ids.append(clip["id"])
        recent_types.append(clip["type"])
        beat_index = max(end_beat, beat_index + 1)

    _normalize_durations(clips, montage_cuts, audio_duration)
    reasoning = _build_reasoning(sections, montage_cuts)
    if action_sync:
        reasoning += " Action peaks aligned to cut grid (not effect-only sync)."

    return {
        "audio_start": "0:00",
        "audio_duration": round(audio_duration, 3),
        "clips": clips,
        "reasoning": reasoning,
        "montage_cuts": montage_cuts,
    }


def _normalize_durations(
    edit_clips: list[dict],
    montage_cuts: list[dict],
    audio_duration: float,
) -> None:
    if not edit_clips:
        return

    total = sum(float(clip["duration"]) for clip in edit_clips)
    delta = round(audio_duration - total, 3)
    if abs(delta) <= DURATION_TOLERANCE:
        return

    last_edit = edit_clips[-1]
    last_cut = montage_cuts[-1]
    adjusted = max(MIN_CLIP_DURATION, round(float(last_edit["duration"]) + delta, 3))
    last_edit["duration"] = adjusted
    last_cut["duration"] = adjusted


def _normalize_audio_path(audio_override: str, beats_data: dict) -> str:
    if audio_override:
        audio_path = Path(audio_override).resolve()
        try:
            return f"bgm/{audio_path.name}" if audio_path.parent == (ROOT / "bgm") else str(audio_path.relative_to(ROOT))
        except ValueError:
            return f"bgm/{audio_path.name}"
    beats_audio = beats_data.get("audio", "")
    if beats_audio:
        beats_path = Path(beats_audio)
        if beats_path.is_absolute():
            try:
                return str(beats_path.relative_to(ROOT))
            except ValueError:
                return f"bgm/{beats_path.name}"
        return beats_audio
    return "bgm/sample.mp3"


def build_montage(
    beats_data: dict,
    manifest: list[dict],
    audio_override: str,
    config: dict,
    rng: random.Random,
    action_sync: bool = True,
    sync_mode: str = "auto",
    cut_grid: dict | None = None,
) -> dict:
    mode = sync_mode
    if mode == "auto":
        mode = "reference" if _can_reference_sync(manifest) else "beat"

    if mode == "beat_replace":
        if not cut_grid:
            raise ValueError("cut_grid required for beat_replace sync mode")
        edit_plan = build_edit_plan_beat_replace(beats_data, manifest, cut_grid, rng, action_sync=action_sync)
    elif mode == "reference":
        edit_plan = build_edit_plan_reference(beats_data, manifest)
    else:
        edit_plan = build_edit_plan(beats_data, manifest, rng, action_sync=action_sync)
    valid, errors = validate_edit_plan(edit_plan)
    if not valid:
        raise ValueError("Invalid EditPlan:\n- " + "\n- ".join(errors))

    audio_path = _normalize_audio_path(audio_override, beats_data)
    return {
        "title": config["douyin"]["title"],
        "audio": audio_path,
        "fps": config["fps"],
        "width": config["width"],
        "height": config["height"],
        "playbackRate": config.get("playback_rate", 1.01),
        "duration": beats_data["duration"],
        "bpm": beats_data["bpm"],
        "sections": beats_data["sections"],
        "beats": beats_data["beats"],
        "editPlan": {
            "audio_start": edit_plan["audio_start"],
            "audio_duration": edit_plan["audio_duration"],
            "reasoning": edit_plan["reasoning"],
            "clips": edit_plan["clips"],
        },
        "cuts": edit_plan["montage_cuts"],
        "validation": {"valid": True, "errors": []},
        "syncMode": mode,
    }


def main() -> None:
    args = parse_args()
    beats_path = Path(args.beats).resolve()
    manifest_path = Path(args.manifest).resolve()
    config_path = ROOT / "config.json"
    output_name = "montage.json" if args.finalize else "montage.draft.json"
    output_path = Path(args.output).resolve() if args.output else ROOT / "output" / output_name

    beats_data = _load_json(beats_path)
    manifest = _load_json(manifest_path)
    config = _load_json(config_path)
    rng = random.Random(args.seed)

    cut_grid = None
    if args.cut_grid:
        cut_grid = _load_json(Path(args.cut_grid).resolve())
    elif args.sync_mode == "beat_replace":
        stem = beats_path.stem.replace("beats.", "", 1) if beats_path.stem.startswith("beats.") else beats_path.stem
        default_grid = ROOT / "output" / f"cut_grid.{stem}.json"
        if default_grid.exists():
            cut_grid = _load_json(default_grid)

    montage = build_montage(
        beats_data,
        manifest,
        args.audio,
        config,
        rng,
        action_sync=args.action_sync,
        sync_mode=args.sync_mode,
        cut_grid=cut_grid if isinstance(cut_grid, dict) else None,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(montage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved montage ({len(montage['cuts'])} cuts): {output_path}")
    print(f"EditPlan valid: {montage['validation']['valid']} | {montage['editPlan']['reasoning']}")

    edit_plan_path = Path(args.edit_plan).resolve() if args.edit_plan else output_path.with_name("edit-plan.json")
    edit_plan_path.write_text(
        json.dumps(montage["editPlan"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved edit plan: {edit_plan_path}")


if __name__ == "__main__":
    main()
