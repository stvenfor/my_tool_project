---
name: cffex-daily-video
description: End-to-end CFFEX daily futures report video pipeline — fetch position data, render PNG/MP4 with Remotion, generate Douyin metadata, and publish. Use when the user asks to generate, render, preview, or publish CFFEX/中信期货持仓 videos, run cffex:daily, or automate the daily report video workflow.
---

# CFFEX 日报视频生成

从 CFFEX 抓取中信期货持仓数据 → 生成静态图 → Remotion 渲染竖屏 MP4 → 发布到抖音。

## 快速命令

| 步骤 | 命令 |
|------|------|
| 全流程（数据+图+视频+抖音配置） | `npm run cffex:daily` |
| 指定日期 | `npm run cffex:daily -- --date 20260710` |
| 周末强制运行 | `npm run cffex:daily -- --force` |
| 仅重渲染视频 | `npm run cffex:video -- --json _cffex/output/citic-net-positions-YYYYMMDD.json --output _cffex/output/citic-net-positions-YYYYMMDD.mp4` |
| 发布到抖音 | `npm run cffex:publish` |
| 发布指定日期 | `npm run cffex:publish -- --date 20260710` |
| 抖音扫码登录 | `npm run cffex:auth` |
| 安装抖音发布依赖 | `npm run cffex:setup-douyin` |
| Remotion 预览 | `cd scripts/cffex-daily/remotion && npm run preview` |
| 安装定时任务（22:00） | `npm run cffex:schedule` |

## Agent 工作流

用户要求「生成今日/某日持仓视频」或「发布到抖音」时，按此清单执行：

```
Task Progress:
- [ ] Step 1: 确认依赖（见下方「首次安装」）
- [ ] Step 2: 运行 npm run cffex:daily（或 --date / --force）
- [ ] Step 3: 检查输出文件（PNG / JSON / MP4 / douyin JSON）
- [ ] Step 4: 若用户要发布，运行 npm run cffex:publish
- [ ] Step 5: 回报产物路径与发布结果
```

### Step 1 — 首次安装（缺依赖时）

```bash
# Python 依赖
pip3 install Pillow playwright

# Remotion 依赖（首次或 node_modules 缺失时）
cd scripts/cffex-daily/remotion && npm install

# 抖音登录与发布依赖（首次发布前）
npm run cffex:setup-douyin   # 若无 node_modules
npm run cffex:auth
```

### Step 2 — 生成视频

在项目根目录执行：

```bash
npm run cffex:daily
```

**输出目录**（默认 `_cffex/output/`）：

| 文件 | 说明 |
|------|------|
| `citic-net-positions-YYYYMMDD.png` | 720×1280 静态报告图 |
| `citic-net-positions-YYYYMMDD.json` | 报告数据（Remotion props） |
| `citic-net-positions-YYYYMMDD.mp4` | 竖屏动画视频（约 7.5s，含 BGM） |
| `citic-net-positions-YYYYMMDD-douyin.json` | 抖音发布配置（按日期归档） |
| `douyin-video.json` | 最新一条抖音发布配置（便于直接发布） |

**跳过条件**：周末且无 `--force` 时自动跳过；非交易日 CFFEX 无数据时正常退出。

### Step 3 — 验证产物

- MP4 存在且非空
- JSON 含 `trade_date`、`citic_by_symbol`、`citic_total` 等字段
- `douyin-video.json` 已自动生成，含 `videoPath`、`title`、`description`、`tags`
- 视频渲染失败时 stderr 会显示 `Video render skipped`；可单独重跑 video 命令

### Step 4 — 发布到抖音

`fetch_and_render.py` 已自动生成抖音配置，无需手动编写 JSON。

```bash
npm run cffex:publish
# 或指定日期
npm run cffex:publish -- --date 20260710
```

常用选项：

| 选项 | 说明 |
|------|------|
| `--dry-run` | 填完表单不发布 |
| `--skip-music` | 跳过选音乐（视频已含 BGM 时推荐） |
| `--keep-open` | 完成后不关闭浏览器 |

发布脚本会自动：上传视频 → 填标题/描述 → 选热门音乐 → AI 封面 → 添加「内容由AI生成」声明。

## 配置

主配置：`scripts/cffex-daily/config.json`

| 字段 | 说明 |
|------|------|
| `output_dir` | 输出目录（默认 `_cffex/output`） |
| `logo_handle` | 视频水印账号（默认 `@小水獭学AI`） |
| `bgm.enabled` / `bgm.volume` | 背景音乐开关与音量 |
| `chart_width` / `chart_height` | 图表尺寸 |
| `douyin.tags` | 抖音话题标签（最多 5 个） |

BGM 文件：`scripts/cffex-daily/bgm.mp3`（不存在则视频无背景音乐）。

抖音发布脚本：`scripts/cffex-daily/douyin/`（项目内，与 skill 同源）。

## 修改视频样式

Remotion 源码在 `scripts/cffex-daily/remotion/src/`：

| 文件 | 职责 |
|------|------|
| `CiticReportVideo.tsx` | 主画面、动画时序 |
| `AnimatedBarChart.tsx` | 柱状图动画 |
| `constants.ts` | 帧数（HOLD 45 + ANIM 180 = 225 帧 @30fps） |
| `types.ts` | 主题色、数据类型 |

修改 Remotion 代码时，读取 `remotion-video-creation` skill 获取领域最佳实践。

## 故障排查

| 现象 | 处理 |
|------|------|
| CFFEX 404 / 无数据 | 非交易日，换 `--date` 或等下一交易日 |
| Playwright 不可用 | 自动降级 Pillow 静态图；视频仍可用 Remotion 渲染 |
| Remotion render 失败 | `cd scripts/cffex-daily/remotion && npm install`，再重跑 video 命令 |
| 视频无声音 | 确认 `bgm.mp3` 存在且 `bgm.enabled: true` |
| 抖音未登录 | `npm run cffex:auth` |
| 发布按钮 disabled | 等视频上传完成；检查标题/描述是否已填 |

更多抖音 DOM 选择器见 [reference.md](reference.md)。

## 相关 Skill

- **remotion-video-creation**：Remotion 动画、音频、图表等实现细节
