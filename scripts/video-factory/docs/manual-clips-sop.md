# Manual Clips SOP

Replace generated placeholders with final visuals without re-voicing.

## Naming

| Mode | Directory | Pattern |
|------|-----------|---------|
| narration | `manual_clips/` | `S{nn}.mp4` or phase name matching `clips_manifest.json` |
| dialogue | `clips/` | `S01.png` … `S15.png` (match `script.json` segment ids) |
| talking_head | `clips/` | `presenter.mp4` or replace `presenter.png` |

## Workflow

1. Run pipeline once to generate `jimeng-prompts.md` (dialogue) or `storyboard.json` (narration).
2. Generate images/videos in 即梦 / 豆包.
3. Copy files into the clip directory using exact shot ids.
4. Re-run with voice skipped:

```bash
npm run video-factory:pipeline -- --id workplace-ep01 --skip-voice
```

## Series inheritance

Projects under the same `series` auto-inherit tags, BGM volume, and voice defaults from `_video-factory/assets/series/{series}.json`.

## Character consistency

Dialogue projects merge `character_voices` from `_video-factory/assets/characters/{key}.json` when not set in `script.json`.
