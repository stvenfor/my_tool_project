---
name: cognitive-video
description: End-to-end cognitive/explainer Douyin short video pipeline — analyze reference, generate script, TTS, B-roll, Remotion render, Douyin publish. Use when the user asks to generate, render, preview, or publish cognitive/认知提升 style Douyin videos, run cognitive:* commands, or automate the cognitive-video workflow.
---

# Cognitive Video Pipeline

## When to use

- User wants 认知类 / cognitive explainer Douyin MP4 videos
- User asks to run `cognitive:pipeline`, render, or publish
- User references `_cognitive-video/` or `scripts/cognitive-video/`

## Quick commands

| Step | Command |
|------|---------|
| Setup | `npm run cognitive:setup` |
| Full pipeline | `npm run cognitive:pipeline -- --id <topic-id>` |
| Skip ref download | `npm run cognitive:pipeline -- --id <topic-id> --skip-analyze` |
| LLM script | `npm run cognitive:script -- --config _cognitive-video/<id>/config.json --llm` |
| Whisper align | `npm run cognitive:align -- --config _cognitive-video/<id>/config.json` |
| Publish | `npm run cognitive:publish -- --config _cognitive-video/<id>/douyin-video.json` |
| Batch | `npm run cognitive:batch -- --all` |

## Work dir

`_cognitive-video/{topic-id}/`

Key files: `config.json`, `script.json`, `subtitles.json`, `storyboard.json`, `output/final.mp4`, `douyin-video.json`

## Checklist

1. Ensure `npm run cognitive:setup` completed (Python + Remotion deps)
2. Copy `scripts/cognitive-video/config.template.json` → `_cognitive-video/{id}/config.json`
3. Run pipeline; if Douyin download fails, use `--skip-analyze` with `asset_mode: placeholder`
4. Verify `output/final.mp4` duration ~ config `duration_sec`
5. Export/publish via `douyin-video.json`

See [scripts/cognitive-video/README.md](../../scripts/cognitive-video/README.md) for full docs.
