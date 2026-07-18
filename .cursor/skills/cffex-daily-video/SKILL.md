---
name: cffex-daily-video
description: End-to-end CFFEX/中信期货净持仓日报流水线 — 抓取数据、渲染 PNG/MP4、gpt-image-2 Infographic 美化图文、抖音图文/视频发布，以及交易日 21:00 LaunchAgent 自动发布。Use when the user asks to generate/beautify/publish CFFEX daily reports, 定时/停止自动发抖音, cffex:daily, cffex:schedule, or Douyin imagetext.
---

# CFFEX 日报全流程

**默认路径**：生成底图 → Infographic Engine 美化 → 抖音图文发布。  
**定时**：交易日相关每晚 **21:00**（每天触发；周末/无数据在脚本内跳过），执行完毕后再发布。

无人值守美化走 **OpenAI `gpt-image-2`**（`beautify_report.py`），不依赖 Cursor Agent；手动调试仍可用 Cursor GenerateImage。

## 快速命令

| 步骤 | 命令 |
|------|------|
| 数据+PNG+MP4 | `npm run cffex:daily` / `--date YYYYMMDD` |
| 仅美化 | `npm run cffex:beautify -- --date YYYYMMDD` |
| 发布美化图文 | `npm run cffex:publish-imagetext -- --date YYYYMMDD --image <png>` |
| 全链路（生成→美化→图文） | `npm run cffex:pipeline` |
| 发布视频（可选） | `npm run cffex:publish -- --date YYYYMMDD` |
| 安装 21:00 定时 | `npm run cffex:schedule` |
| 卸载定时 | `npm run cffex:unschedule` |
| 定时状态 | `npm run cffex:schedule-status` |
| 停止自动发送 | `npm run cffex:auto-off` |
| 恢复自动发送 | `npm run cffex:auto-on` |
| 抖音登录 | `npm run cffex:auth` |

## Agent 工作流（手动美化图文）

```
Task Progress:
- [ ] Step 1: 依赖（Pillow/playwright、remotion、cffex:setup-douyin、cffex:auth）
- [ ] Step 2: npm run cffex:daily（或 --date）
- [ ] Step 3: 校验 PNG/JSON
- [ ] Step 4: cffex:beautify 或 Cursor GenerateImage（Infographic Engine）
- [ ] Step 5: cffex:publish-imagetext
- [ ] Step 6: 回报路径与发布结果
```

定时任务勿提交 Codex；勿在 Agent 里重复装定时 unless 用户要求。

## 定时行为

[`run.sh`](../../modules/cffex-daily/run.sh)：

1. `schedule.auto_publish=false` → 日志 skip，退出 0  
2. `fetch_and_render.py`（周末 skip → 无 PNG → 不发布）  
3. `beautify_report.py`（需 `OPENAI_API_KEY` + 风格参考图）  
4. `publish-imagetext-to-douyin.mjs`（美化成功后才发）

配置：[`modules/cffex-daily/config.json`](../../modules/cffex-daily/config.json) 的 `schedule` / `beautify`。

前置：机器 21:00 开机且已登录 GUI；抖音 profile 有效；Chrome 可用。

## 产物

| 路径 | 说明 |
|------|------|
| `modules/cffex-daily/work/output/citic-net-positions-*.png` | 底图 |
| `_hot-topic-infographic/beautified/cffex-position-report-*-auto-vN.png` | 定时/CLI 美化图 |
| `modules/cffex-daily/work/logs/daily-*.log` | 全链路日志 |

## 故障排查

| 现象 | 处理 |
|------|------|
| beautify 失败 OPENAI_API_KEY | 导出 key；写入 `~/.codex/.env` 或 launchd EnvironmentVariables |
| 风格参考缺失 | 配置 `beautify.style_reference` 指向现有美化图 |
| 图文登录失败 | `npm run cffex:auth` |
| 定时未跑 | `cffex:schedule-status`；确认已登录用户会话 |
| 误点高清发布 | 使用项目内 `publish-imagetext.mjs`（页脚「发布」） |

更多：[reference.md](reference.md) · [beautify-prompt.md](beautify-prompt.md)
