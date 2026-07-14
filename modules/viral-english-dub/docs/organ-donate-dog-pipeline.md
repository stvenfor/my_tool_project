# 病毒短剧英文配音链路：器官捐献样例（organ-donate-dog）

> 仓库：`my_tool_project`  
> 流水线代码：`modules/viral-english-dub/`  
> 样例工作目录：`modules/viral-english-dub/work/organ-donate-dog/`  
> 文档日期：2026-07-14  
> 目标：把中文口播短剧做成「角色原音色 + 中文腔英文 + 保留 BGM + 双语字幕」的抖音成片

---

## 1. 项目目标

将热门中文短剧片段（本文以「器官捐献 AI 短剧」为例）自动做成英文配音视频：

| 目标 | 做法 |
|------|------|
| 台词忠实 | Whisper 转写 → LLM/人工校对 → `script.json` |
| 音色像原角色 | CosyVoice2 zero-shot，用**该句中文人声**作 prompt |
| 英语读完 | `prefer_complete`，禁止硬裁切半截英文 |
| 口型时间轴可对齐 | 英文偏长时**画面轻减速**（`timeline.json` + Remotion） |
| 保留氛围 | Demucs 分离 `no_vocals` 作 BGM，侧链闪避人声 |
| 字幕 | Remotion 底部英/中双语；遮罩盖原片烧录字幕 |

**参考样例（只读、勿改）**：杨过断臂音色参考片 `506b7c6d…mp4`，用于听感 benchmark，不作为本样例输入。

**本样例输入**：微信本地 MP4 `e1237b84…mp4` → 工作目录 `organ-donate-dog`。

---

## 2. 成片与工作目录

### 2.1 关键出入

- **输入**：`config.json` → `target_input`（本地 mp4）
- **输出成片**：`modules/viral-english-dub/work/organ-donate-dog/final.mp4`
- **抖音元数据**：`douyin-video.json`（可选发布）

### 2.2 推荐分辨率

器官捐献样例原片为横屏 letterbox 样式：

- `width`: 1280
- `height`: 640
- `fps`: 30
- `duration_sec`（源片时长）：约 31.633s  
- 重定时后成片墙钟时长可能更长（英文未删时，约 32–33s）

### 2.3 工作目录结构（关键）

```text
modules/viral-english-dub/work/organ-donate-dog/
├── config.json                 # 流水线配置（唯一权威参数）
├── script.json                 # 中英台词 + 说话人 + prompt 路径
├── subtitles.json              # Remotion 字幕（重定时后的墙钟时间）
├── timeline.json               # 视频重定时片段 + 旁白落点
├── alignment.json              # 对齐摘要
├── audio_mix.json              # 混音参数回写
├── storyboard.json             # Remotion 渲染输入
├── narration.wav               # 英文旁白时间线混音
├── narration_clean.wav         # 去噪后旁白
├── final_audio.wav             # BGM + 旁白成片音轨
├── final.mp4                   # 最终视频
├── douyin-video.json
├── reference/
│   ├── source.mp4              # 拷贝后的原片
│   ├── transcript.json
│   ├── speakers.json
│   ├── bgm_stem.wav            # Demucs no_vocals
│   ├── bgm_smooth.wav          # 平滑后的 BGM 床
│   ├── segment_prompts/        # 每句中文人声 prompt
│   └── speaker_spk*_prompt.*
└── segments/
    ├── manifest.json           # 合成结果清单（含 raw/fitted 时长）
    ├── seg_XX_raw.wav          # CosyVoice 原生长度
    └── seg_XX.wav              # prefer_complete 拟合后
```

---

## 3. 技术栈与环境

| 模块 | 技术 |
|------|------|
| 转写 | OpenAI Whisper（`whisper_model`，常用 `base`） |
| 人声/BGM 分离 | Demucs `htdemucs` two-stems |
| 说话人 | 启发式 gap / 可选 diarize；本样例用 `speaker_assignments` 固定 |
| 翻译 | LLM（`use_llm_translate`）或人工改 `script.json` |
| 克隆 TTS | CosyVoice2-0.5B zero-shot（默认） |
| 对齐 / 重定时 | `align_audio.py` → `timeline.json` |
| 混音去噪 | ffmpeg（`afftdn` / `anlmdn` / `agate` / `sidechaincompress`） |
| 画面+字幕 | Remotion `ViralDubVideo` |
| 发布（可选） | Playwright 抖音创作者中心 |

### 3.1 一次性安装

```bash
cd /path/to/my_tool_project
npm run viral-dub:setup
npm run viral-dub:setup-cosyvoice   # CosyVoice + Matcha-TTS + 模型
```

CosyVoice 代码与模型落点：

- `modules/viral-english-dub/vendor/CosyVoice`
- `modules/viral-english-dub/pretrained_models/CosyVoice2-0.5B`

依赖：Python 3.12+、ffmpeg、Node（Remotion）、可选 CUDA/MPS。

---

## 4. 端到端流程图

```text
原片 MP4
  │
  ▼
analyze_reference.py     → reference/source.mp4 + transcript.json
  │
  ▼
separate_bgm.py          → bgm_stem.wav + vocals（供 prompt）
  │
  ▼
diarize_speakers.py      → speakers + segment_prompts + 写入 script 骨架字段
  │
  ▼
translate_script.py      → script.json（en / text_zh / speaker_id）
  │   （强烈建议人工校对 Whisper 错字与英文长度）
  ▼
synthesize_voice.py      → seg_XX_raw.wav → seg_XX.wav（prefer_complete）
  │
  ▼
align_audio.py           → narration.wav + timeline.json + subtitles.json
  │
  ▼
mix_audio.py             → narration_clean.wav + bgm_smooth.wav → final_audio.wav
  │
  ▼
build_storyboard.py      → storyboard.json（含 video_pieces）
  │
  ▼
render.mjs (Remotion)    → final.mp4
  │
  ▼
export_douyin.py         → douyin-video.json（可选 publish）
```

一键入口：

```bash
npm run viral-dub:pipeline -- \
  --input "/绝对路径/原片.mp4" \
  --id organ-donate-dog
```

器官样例已有 `config.json` 时，按阶段重跑更稳（见第 10 节）。

---

## 5. 各阶段说明

### 5.1 分析原片 — `analyze_reference.py`

- 拷贝/下载到 `reference/source.mp4`
- Whisper 出 `transcript.json`（带时间戳）
- 写回分辨率、时长等到 config / manifest

注意：Whisper 对 AI 短剧常有错字（本样例曾把「手术」听成「守树」、「捐献四肢」听成「捐陷四只」），**必须人工校对 `script.json`**。

### 5.2 BGM / 人声分离 — `separate_bgm.py`

- Demucs：`vocals` + `no_vocals`
- `no_vocals` → `reference/bgm_stem.wav`
- `vocals` 用于逐句裁切 prompt（`use_vocal_stem_for_prompts: true`）

### 5.3 说话人与 prompt — `diarize_speakers.py`

器官样例三人声固定赋值（`config.speaker_assignments`）：

| speaker_id | 角色意向 | 出现句（约） |
|------------|----------|--------------|
| `spk0` | 女主 | 捐四肢 / 终于自由 / 到底是谁 / 臭狗… |
| `spk1` | 红狗 | 「别说了主人」 |
| `spk2` | 旁白/他人 | 恭喜你 / 手术要开始 |

每句 `prompt_wav`：`reference/segment_prompts/seg_XX.wav`  
`prompt_text`：该句中文（给 CosyVoice zero-shot 学语气）。

### 5.4 翻译 — `translate_script.py`

原则：

1. 语义忠实，可略压缩英文音节（否则口型窗与读速冲突大）
2. 保留中文腔友好的措辞（`accent_preserve`）
3. 校对后只改 `script.json` 的 `en` / `text_zh`

器官样例部分英文（压缩后）：

| 中文（校正义） | 英文 |
|----------------|------|
| 已经找到为我捐献四肢的人了 | They found a donor for all four of my limbs. |
| 我终于可以自由了 | I can finally be free. |
| 恭喜你啊 | Congratulations. |
| 马上就要手术了 | The surgery is about to begin. |
| 到底是谁啊 | Who is it? |
| 别说了主人 | Stop talking, master. |
| 手术快开始了 | The surgery is starting soon. |
| 臭狗，你居然为了我 | You stupid dog—you actually did this for me. |
| 你怎么能这么傻 | How can you be so foolish? |

### 5.5 合成 — `synthesize_voice.py` + `cosyvoice_clone.py`

- 后端：`voice_clone_backend: cosyvoice`
- 模式：`cosyvoice_mode: zero_shot`
- 调用：`inference_zero_shot(英文, 中文prompt文本, 中文prompt音频)`
- 时长控制：
  1. CosyVoice `speed` 温和重跑（约 0.85–1.35）
  2. `audio_fit_mode: prefer_complete`：只轻度 `atempo`，**永不硬切半截句子**
  3. 超过视频减速上限时，才压到 `target / video_min_playback_rate`

保留 `seg_XX_raw.wav` 便于事后重拟合。

### 5.6 对齐与画面重定时 — `align_audio.py`

输出 `timeline.json`：

- **speech**：源片 `[src_start, src_end]` 映射到墙钟 `out_*`；若英文更长，则 `playback_rate < 1`（减速）
- **gap**：句间留白 1x 播放
- 旁白按 `speech_placements.start_sec` 用 `adelay+amix` 落到 `narration.wav`
- 字幕时间改用墙钟时间（与重定时一致）

关键配置：

- `video_min_playback_rate`: 0.72（英文最长可扩到约中文时长 ÷ 0.72）
- `video_max_playback_rate`: 1.28

### 5.7 混音去噪 — `mix_audio.py`

器官样例音频问题曾出现两类：

1. **克隆底噪 / 嘶声** → `denoise_strength: strong`（FFT + NLM + 句间 gate + loudnorm）
2. **BGM 不平滑 / 压过人声** → 平滑床 + 侧链闪避 + 音量约 0.42

**关键踩坑（已修）**：`sidechaincompress` 会消费掉一侧音频标签。混音时必须用 `asplit` 分出旁白副本，否则成片只剩很轻的 BGM、**人声消失**。

正确形态示意：

```text
[旁白] → asplit → [vox]      ──┐
                 → [vox_sc] ──┼→ sidechaincompress → [bgm_ducked] ─┐
[平滑BGM] ────────────────────┘                                      ├→ amix → final_audio
[vox] ───────────────────────────────────────────────────────────────┘
```

### 5.8 字幕遮罩与构图 — Remotion

- 组件：`remotion/src/ViralDubVideo.tsx`
- `video_pieces`：按 `timeline.json` 切段 + `playbackRate`
- 器官样例遮罩（盖上下黑边/硬字幕区）：

```json
"subtitle_mask": {
  "top_pct": 0.11,
  "bottom_pct": 0.14,
  "color": "#000000"
}
```

- 双语字幕默认 `position: bottom`（`subtitle_position`）

### 5.9 渲染 — `render.mjs`

```bash
node modules/viral-english-dub/render.mjs \
  --storyboard modules/viral-english-dub/work/organ-donate-dog/storyboard.json \
  --work-dir modules/viral-english-dub/work/organ-donate-dog \
  --output modules/viral-english-dub/work/organ-donate-dog/final.mp4
```

### 5.10 导出 / 发布（可选）

```bash
npm run viral-dub:export -- --config modules/viral-english-dub/work/organ-donate-dog/config.json
npm run viral-dub:publish -- --config modules/viral-english-dub/work/organ-donate-dog/config.json
```

---

## 6. 器官样例当前关键配置（摘要）

路径：`modules/viral-english-dub/work/organ-donate-dog/config.json`

| 字段 | 值 | 含义 |
|------|----|------|
| `clip_id` | `organ-donate-dog` | 工作目录名 |
| `voice_clone_backend` | `cosyvoice` | 默认克隆后端 |
| `cosyvoice_mode` | `zero_shot` | 用中文文本+音频学语气 |
| `use_inline_prompt` | `true` | 每句独立 prompt |
| `audio_fit_mode` | `prefer_complete` | 完整读完优先 |
| `max_stretch_ratio` | `1.22` | 软变速上限 |
| `video_min_playback_rate` | `0.72` | 说话段最慢画面 |
| `keep_bgm` | `true` | 保留 BGM |
| `bgm_volume` | `0.42` | BGM 床音量 |
| `bgm_sidechain_duck` | `true` | 对人闪避 |
| `denoise_strength` | `strong` | 强去噪 |
| `hide_original_subtitles` | `true` | 开遮罩 |
| `show_subtitles` | `true` | 双语字幕 |
| `disallow_tts_fallback` | `true` | 禁止退回 edge-tts |

---

## 7. npm 脚本速查

```bash
npm run viral-dub:setup
npm run viral-dub:setup-cosyvoice
npm run viral-dub:pipeline -- --input "<mp4>" --id organ-donate-dog

npm run viral-dub:analyze -- --config modules/viral-english-dub/work/organ-donate-dog/config.json
npm run viral-dub:separate-bgm -- --config ...
npm run viral-dub:diarize -- --config ...
npm run viral-dub:translate -- --config ...
npm run viral-dub:voice -- --config ...
npm run viral-dub:align -- --config ...
npm run viral-dub:mix-audio -- --config ...
npm run viral-dub:build -- --config ...
npm run viral-dub:render -- \
  --storyboard modules/viral-english-dub/work/organ-donate-dog/storyboard.json \
  --work-dir modules/viral-english-dub/work/organ-donate-dog \
  --output modules/viral-english-dub/work/organ-donate-dog/final.mp4
npm run viral-dub:export -- --config ...
```

---

## 8. 日常迭代推荐路径

### 8.1 只改英文文案

1. 编辑 `script.json` 的 `en`
2. `viral-dub:voice` → `align` → `mix-audio` → `build` → `render`

### 8.2 音色不满意

1. 确认该句 `prompt_wav` 是否干净（应用 vocal stem）
2. 检查 `prompt_text` 与原文一致
3. 避免对同一句反复 exact stretch；看 `seg_XX_raw.wav` 自然读感

### 8.3 只修杂音 / BGM（无需重合成）

```bash
npm run viral-dub:mix-audio -- --config modules/viral-english-dub/work/organ-donate-dog/config.json
npm run viral-dub:build -- --config modules/viral-english-dub/work/organ-donate-dog/config.json
npm run viral-dub:render -- --storyboard modules/viral-english-dub/work/organ-donate-dog/storyboard.json \
  --work-dir modules/viral-english-dub/work/organ-donate-dog \
  --output modules/viral-english-dub/work/organ-donate-dog/final.mp4
```

可调：`denoise_strength`（`strong|light|off`）、`bgm_volume`、`bgm_duck_*`。

### 8.4 从 raw 重拟合时长（不重新 CosyVoice）

若已有 `seg_XX_raw.wav`，可用 `lib.fit_audio_prefer_complete` 批量重拟合后走 align→mix→render（历史排障路径）。

---

## 9. 已知限制与验收标准

### 9.1 限制（需对用户说清）

1. **跨语种不可能逐音素口型**：画面仍是中文口型；减速只是拉长说话窗，改善「对不上」的主观感受。
2. **英文天然更长**：过长句需压缩翻译，或接受成片略长于原片。
3. **Whisper 不可信**：剧本必须人工听校。
4. **完美嘴型重绘**需额外方案（如 Wav2Lip），当前流水线未接。

### 9.2 验收清单

- [ ] 每句英文可完整听完，无半截断句
- [ ] 开嗓时刻大致落在角色张嘴时段（允许轻微减速感）
- [ ] 音色可辨认角色差异（女主 / 狗 / 旁白）
- [ ] BGM 连续，说话时自动让路，无明显爆炸或死静
- [ ] 无刺耳嘶声、人声未丢失
- [ ] 原片烧录字幕被上下遮罩盖住；底部英中字幕可读
- [ ] `final.mp4` 音视频同步，时长与 `timeline.json` 一致

---

## 10. 相关文件索引

| 路径 | 作用 |
|------|------|
| `modules/viral-english-dub/README.md` | 短 README |
| `modules/viral-english-dub/run_pipeline.py` | 编排入口 |
| `modules/viral-english-dub/cosyvoice_clone.py` | CosyVoice 封装 |
| `modules/viral-english-dub/lib.py` | 时长拟合 / 工具函数 |
| `modules/viral-english-dub/mix_audio.py` | 去噪 + 平滑 BGM + 侧链 |
| `modules/viral-english-dub/align_audio.py` | 重定时时间线 |
| `modules/viral-english-dub/remotion/src/ViralDubVideo.tsx` | 成片合成 |
| `modules/viral-english-dub/config.template.json` | 默认配置模板 |
| `modules/viral-english-dub/work/organ-donate-dog/*` | 本样例全部产物 |

---

## 11. 同流水线其他样例

| clip_id | 说明 |
|---------|------|
| `organ-donate-dog` | 器官捐献横屏样例（本文） |
| `cat-ai-trash` | 猫猫竖屏短剧；中间硬字幕遮罩策略不同 |
| `yang-guo-arm` | 参考音色样例工作区（若存在） |

竖屏猫片注意：中间厚黑条体验差，宜关 `center_*` 厚遮罩，字幕改底部描边。

---

## 12. 变更备忘（2026-07 迭代）

1. 克隆默认后端：Sopro → **CosyVoice2 zero-shot**
2. 对齐策略：exact 硬塞中文槽 → **prefer_complete + 视频减速重定时**
3. 音频：强去噪 + BGM 平滑侧链；修复 **asplit 人声丢失** bug
4. 配置沉淀：`denoise_strength` / `bgm_sidechain_duck` / `video_min_playback_rate`

---

*本文档由流水线实跑整理，同步至飞书知识库「AI项目」。本地副本：`modules/viral-english-dub/docs/organ-donate-dog-pipeline.md`。*
