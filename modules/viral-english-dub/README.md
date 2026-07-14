# Viral English Dub Pipeline

Hot clip → faithful English translation → CosyVoice zero-shot clone (keep original timbre/prosody) → bilingual Douyin video.

## Quick start

```bash
npm run viral-dub:setup
npm run viral-dub:setup-cosyvoice   # first time: CosyVoice + Matcha-TTS + model
npm run viral-dub:pipeline -- --input "/path/to/clip.mp4" --id my-clip
```

## Stages

1. `analyze_reference.py` — local/URL input, Whisper zh transcript
2. `diarize_speakers.py` — speaker tags + prompt audio per line
3. `translate_script.py` — faithful zh→en (LLM or fallback)
4. `synthesize_voice.py` — CosyVoice zero-shot (default) using each line's Chinese audio+text as prompt
5. `align_audio.py` — timeline alignment → narration.wav + subtitles.json
6. `separate_bgm.py` / `mix_audio.py` — keep BGM, replace vocals
7. `build_storyboard.py` + `render.mjs` — Remotion ViralDubVideo
8. `export_douyin.py` — douyin-video.json

## Voice config

| Field | Effect |
|-------|--------|
| `voice_mode` | `cross_lingual_clone` or `edge-tts` |
| `voice_clone_backend` | `cosyvoice` (default), `sopro`, or `zipvoice` |
| `cosyvoice_mode` | `zero_shot` (uses Chinese prompt text+wav for prosody) or `cross_lingual` |
| `use_inline_prompt` | each English line clones from that line's original Chinese audio |
| `accent_preserve` | LLM prompt: Chinese-accent friendly English |
| `audio_fit_mode` | `trim_pad` (default, preserves timbre) or `stretch` |

Re-voice only: `npm run viral-dub:voice -- --config modules/viral-english-dub/work/<id>/config.json`

## Output

- `modules/viral-english-dub/work/{id}/final.mp4`
- `modules/viral-english-dub/work/{id}/douyin-video.json`
