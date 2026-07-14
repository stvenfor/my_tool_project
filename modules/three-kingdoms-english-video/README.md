# Three Kingdoms English Video Pipeline

Replicate Douyin「艾妈AI英语动画」儿童英语+三国系列（如【移驾许昌】）。

## Quick start

```bash
npm run tk-english:setup
npm run tk-english:analyze -- --skip-whisper
npm run tk-english:pipeline -- --episode yijia-xuchang
npm run tk-english:parity -- --reference modules/three-kingdoms-english-video/work/reference/yijia-xuchang/reference/source.mp4 --replica modules/three-kingdoms-english-video/work/output/yijia-xuchang/final.mp4 --subtitles modules/three-kingdoms-english-video/work/output/yijia-xuchang/subtitles.json
```

## Stages

1. `analyze_reference.py` — 下载抖音参考片，切点/风格/转写
2. `generate_script.py` — 英中双语脚本
3. `synthesize_voice.py` — edge-tts 童声英文
4. `map_narration_shots.py` + `fetch_clips.py` — 参考片切片或 `manual_clips/` 导入
5. `build_storyboard.py` + `render.mjs` — Remotion 合成 9:16
6. `parity_check.py` — 时长/画幅/SSIM 验收
7. `douyin-video.json` + `tk-english:publish` — 抖音发布

## 手工复刻（豆包→即梦→剪映）

见 [`modules/three-kingdoms-english-video/work/manual/yijia-xuchang/SOP.md`](../../modules/three-kingdoms-english-video/work/manual/yijia-xuchang/SOP.md) 与 `storyboard_prompts.json`。

将即梦导出的 `S00.mp4`…`S12.mp4` 放入 `manual_clips/` 后重新跑 pipeline。

## Output

- `modules/three-kingdoms-english-video/work/output/yijia-xuchang/final.mp4`
- `modules/three-kingdoms-english-video/work/output/yijia-xuchang/douyin-video.json`
