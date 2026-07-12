# Cognitive Video Pipeline

Reusable Douyin-style cognitive/explainer short video workflow.

## Quick start

```bash
npm run cognitive:setup
npm run cognitive:pipeline -- --id middle-class-exit
```

Skip reference download (use template script + placeholder B-roll):

```bash
npm run cognitive:pipeline -- --id middle-class-exit --skip-analyze
```

Stickman line-art visuals (matches 火柴人笔记 style, no stock footage):

```bash
# config: "asset_mode": "stickman"
npm run cognitive:pipeline -- --id middle-class-exit --skip-analyze
```

## Stages

1. `analyze_reference.py` — download Douyin ref, cuts/beats/transcript/style
2. `generate_script.py` — script.json (rule-based or `--llm`)
3. `synthesize_voice.py` — edge-tts Chinese narration
4. `align_whisper.py` — optional Whisper timestamp alignment
5. `fetch_broll.py` — reference slices or placeholder clips
6. `build_storyboard.py` — storyboard.json
7. `render.mjs` — Remotion `CognitiveVideo`
8. `export_douyin.py` — douyin-video.json
9. `publish-to-douyin.mjs` — Playwright publish

## Voice tuning (`config.json`)

| Field | Effect | Current default |
|-------|--------|-----------------|
| `voice_rate` | 语速基准，如 `+12%` | `+12%` |
| `voice_pitch` | 音高，负值更低沉 | `-6Hz` |
| `voice_volume` | TTS 输出音量 | `+5%` |
| `voice_rhythm.strong_clause_gap_ms` | 句号/问号后停顿 | `340` |
| `voice_rhythm.comma_clause_gap_ms` | 逗号后停顿 | `160` |
| `voice_rhythm.pitch_bounce_hz` | 短语间音高起伏 | `4` |
| `voice_rhythm.prosody_by_phase` | 各段落语速/音高偏移 | pain 慢沉，cta 快扬 |
| `voice_rhythm.segment_gap_by_phase` | 段与段之间的呼吸 | pain 最长 |
| `voice_enhance.warmth_db` | 低频厚度 | `2.0` |
| `voice_enhance.presence_db` | 中高频清晰度 | `0.9` |

Re-voice only: `npm run cognitive:voice -- --config _cognitive-video/<id>/config.json`

## Output

- `_cognitive-video/{id}/output/final.mp4`
- `_cognitive-video/{id}/storyboard.json`
- `_cognitive-video/{id}/douyin-video.json`

## Batch

Approved topics live in `topics/approved/{id}/config.json`:

```bash
npm run cognitive:batch -- --all
npm run cognitive:publish -- --config _cognitive-video/middle-class-exit/douyin-video.json --dry-run
```
