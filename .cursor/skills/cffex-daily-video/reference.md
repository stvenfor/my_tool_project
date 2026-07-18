# CFFEX 日报 — 参考

## 目录

```
modules/cffex-daily/
├── fetch_and_render.py
├── render_video.mjs
├── publish-to-douyin.mjs              # 视频发布入口
├── publish-imagetext-to-douyin.mjs    # 图文发布入口
├── config.json
├── bgm.mp3 / logo.png
└── remotion/

modules/shared/douyin/
├── publish-video.mjs
├── publish-imagetext.mjs             # 图文（页脚「发布」，禁「高清发布」）
├── auth.mjs
├── douyin-browser.mjs
└── setup.sh

_hot-topic-infographic/beautified/    # 美化成品归档
```

## 报告 JSON

```json
{
  "trade_date": "20260714",
  "date_label": "2026年07月14日 周二",
  "daily_quote": "…",
  "logo_handle": "@小水獭学AI",
  "citic_by_symbol": { "IH": -1149, "IF": 463, "IC": 105, "IM": -245 },
  "citic_total": -826,
  "top20_net_short_total": 146910,
  "net_buy_total": -939,
  "bgm_enabled": true,
  "bgm_volume": 0.14
}
```

## 抖音视频 JSON

`citic-net-positions-YYYYMMDD-douyin.json` / `douyin-video.json`：

```json
{
  "videoPath": "citic-net-positions-YYYYMMDD.mp4",
  "title": "string ≤30",
  "description": "string，不含 #",
  "tags": ["最多5个，不带 #"]
}
```

## 抖音图文 JSON

`citic-net-positions-YYYYMMDD-imagetext.json`：

```json
{
  "imagePaths": ["/abs/path/to/beautified.png"],
  "title": "可选，≤30",
  "description": "可选",
  "tags": ["最多5个"]
}
```

由 `publish-imagetext-to-douyin.mjs --date --image` 自动从视频元数据生成。

## description 模板

```
{date_label} 中信期货净持仓数据

IH {±IH}  IF {±IF}  IC {±IC}  IM {±IM}
中信合计{净多|净空} {abs(citic_total)}
Top20净空 {top20}  净买入 {net_buy}

{daily_quote}
```

## 关键 URL

| 用途 | URL |
|------|-----|
| 视频上传 | `https://creator.douyin.com/creator-micro/content/upload` |
| 图文上传 | `…/upload?default-tab=3` |
| Profile | `~/.douyin-playwright/profile` |

图文编辑页发布：只点 `button.button-dhlUZE.primary-cECiOJ` 文本为「发布」；不要点「高清发布」。

## Remotion

- ID `CiticReportVideo`，720×1280 @30fps，225 帧

## 定时（21:00 美化图文）

`npm run cffex:schedule` → 每天 21:00 `run.sh`：  
`auto_publish` 门闩 → `fetch_and_render` → `beautify_report.py` → `publish-imagetext`。

- 卸载：`cffex:unschedule`
- 关发送：`cffex:auto-off`（改 `config.json` `schedule.auto_publish`）
- 日志：`modules/cffex-daily/work/logs/daily-YYYYMMDD.log`
- 美化需 `OPENAI_API_KEY` + `beautify.style_reference`
