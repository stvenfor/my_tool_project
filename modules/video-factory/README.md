# Video Factory

Unified pipeline for long-term 口播 content: narration, dialogue drama, and talking-head modes.

## Quick start

```bash
npm run video-factory:setup
npm run video-factory:draft -- --all
npm run video-factory:pipeline -- --id middle-class-exit --init
npm run video-factory:batch -- --all
```

## Modes

| mode | Description |
|------|-------------|
| `narration` | 解说口播 — edge-tts + stickman/B-roll + Remotion |
| `dialogue` | 剧情对白 — multi-voice + image clips + Remotion |
| `talking_head` | 出镜口播 — presenter clip + narration + subtitles |

## Work dir

`modules/video-factory/work/{project-id}/`

## Topic pool

- Draft: `modules/video-factory/topics/draft/*.json`
- Approved: `modules/video-factory/topics/approved/*.json`

```bash
npm run video-factory:approve -- --id worker-salary-silence
npm run video-factory:batch -- --all
```

## Publish queue

```bash
npm run video-factory:queue-sync
npm run video-factory:queue-next
npm run video-factory:publish -- --config modules/video-factory/work/<id>/douyin-video.json --dry-run
```

## Asset library

- Characters: `modules/video-factory/work/assets/characters/{key}.json`
- Series packs: `modules/video-factory/work/assets/series/{series}.json`
- Manual clips SOP: `docs/manual-clips-sop.md`

## QA

```bash
npm run video-factory:qa -- --id workplace-ep01 --save
```
