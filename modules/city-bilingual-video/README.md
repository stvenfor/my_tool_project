# City Bilingual Video Pipeline

Replicate Douyin-style bilingual city travel promos (e.g. 「白天是西安，晚上是长安」).

## Quick start

```bash
npm run city-bilingual:setup
npm run city-bilingual:pipeline -- --config modules/city-bilingual-video/work/output/xian/city.config.json
```

## Stages

1. `analyze_reference.py` — download Douyin reference, extract cuts/beats/style
2. `generate_script.py` — English narration + bilingual subtitles
3. `map_reference_shots.py` + `fetch_city_clips.py` — hybrid asset replacement
4. `synthesize_voice.py` — English edge-tts narration
5. `build_storyboard.py` — assemble `storyboard.json`
6. `render.mjs` — Remotion `CityBilingualVideo`

## Config

Copy [`config.template.json`](config.template.json) to `modules/city-bilingual-video/work/output/{city}/city.config.json` and edit:

- `city_name` / `ancient_name`
- `landmarks_day` / `landmarks_night`
- `reference_url`
- `asset_mode`: `douyin_broll` | `hybrid` | `reference_slice` | `placeholder`
- `douyin_sources`: phase-grouped Douyin seed URLs (see `douyin_sources.template.json`)

## Output

- `modules/city-bilingual-video/work/output/xian/final.mp4`
- `modules/city-bilingual-video/work/output/xian/storyboard.json`
