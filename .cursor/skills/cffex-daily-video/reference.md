# CFFEX 日报视频 — 参考

## 目录结构

```
scripts/cffex-daily/
├── fetch_and_render.py    # 抓数据 + 渲染 PNG/JSON + 调用视频渲染
├── render_video.mjs       # 复制 assets → 调用 remotion render
├── config.json            # 输出目录、BGM、图表尺寸
├── bgm.mp3                # 背景音乐（可选）
├── logo.png               # 水印 logo
├── encouragement_quotes.json  # 每日励志语池
└── remotion/
    ├── src/CiticReportVideo.tsx
    └── public/            # 渲染时临时写入 report-props.json、logo、bgm
```

## 报告 JSON Schema

`fetch_and_render.py` 输出的 JSON 结构：

```json
{
  "trade_date": "20260710",
  "date_label": "2026年07月10日 周五",
  "daily_quote": "方向对了，不怕路远，坚持就是胜利！",
  "logo_handle": "@小水獭学AI",
  "bgm_enabled": true,
  "bgm_volume": 0.14,
  "citic_by_symbol": { "IH": 163, "IF": -24, "IC": 1510, "IM": -126 },
  "citic_total": 1523,
  "top20_net_short_total": 136619,
  "net_buy_total": 6193
}
```

## 抖音发布脚本（项目内）

```
scripts/cffex-daily/douyin/
├── publish-video.mjs
├── auth.mjs
├── douyin-browser.mjs
└── setup.sh
```

便捷入口：`scripts/cffex-daily/publish-to-douyin.mjs`（默认 `--skip-music`，视频已含 BGM）。

## 抖音视频发布 JSON Schema

```json
{
  "videoPath": "string (required, 相对 JSON 目录或绝对路径, .mp4/.mov/.m4v, ≤128MB)",
  "title": "string (optional, ≤30 字)",
  "description": "string (optional, 不含 # 话题)",
  "tags": ["string (optional, max 5, 不带 #)"]
}
```

## 从报告 JSON 生成 description 模板

```
{date_label} 中信期货净持仓数据

IH {sign}{IH}  IF {sign}{IF}  IC {sign}{IC}  IM {sign}{IM}
中信合计{净多/净空} {abs(citic_total)}
Top20净空 {top20_net_short_total}  净买入 {net_buy_total}

{daily_quote}
```

数值格式：`+163` / `-24`（正数带 `+`）。

## 抖音发布关键 URL

| 页面 | URL |
|------|-----|
| 视频上传 | `https://creator.douyin.com/creator-micro/content/upload` |
| 登录 Profile | `~/.douyin-playwright/profile` |

环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `DOUYIN_PROFILE_DIR` | `~/.douyin-playwright/profile` | Playwright 持久化 Profile |
| `DOUYIN_VIDEO_UPLOAD_URL` | 视频上传 URL | 覆盖上传入口 |

## Remotion 渲染参数

- Composition ID: `CiticReportVideo`
- 尺寸: 720×1280（9:16 竖屏）
- FPS: 30
- 总帧数: 225（前 45 帧静态 hold + 180 帧动画）

手动渲染：

```bash
node scripts/cffex-daily/render_video.mjs \
  --json _cffex/output/citic-net-positions-YYYYMMDD.json \
  --output _cffex/output/citic-net-positions-YYYYMMDD.mp4
```

## 定时任务

`npm run cffex:schedule` 安装 LaunchAgent，每天 22:00 执行 `run.sh`。
日志目录：`_cffex/logs/`。
