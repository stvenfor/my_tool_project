---
name: etf-68-daily
description: >-
  Generates the daily 68-ETF technical review: live bars report, interactive
  Cursor canvas (filters/sorts, 30-day hold, drawdowns, best-edge column),
  edge-condition analysis, and dated snapshot archive under
  modules/etf-monitor/reports. Use when the user asks to 生成今日68只ETF,
  ETF明细画布, etf:report, etf-68-daily, 代表池技术面审阅, or sync ETF canvas
  status for a trading day.
---

# 68 只 ETF 日更

工作目录：`modules/etf-monitor`。上海时区日期 `DAY=YYYY-MM-DD`（默认今天）。

## 硬性规则

1. **禁止过期数据**：行情拉取失败就停止并说明原因；不得用昨日报告冒充今日输出。
2. **直连行情**：执行前 `export NO_PROXY='*'`，并 `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy`（本地代理常导致 `public_endpoint_unavailable`）。
3. **画布必出**：报告成功后必须写入 IDE 画布，并归档到 `reports/`。
4. **每次归档**：跑完调用 `save_snapshot.py --date $DAY`。

## 快速命令

```bash
cd modules/etf-monitor
export NO_PROXY='*'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

# 1) 报告（seed=上一份 dated review）
python3.12 generate_review.py \
  --seed reports/representative-technical-review-<PREV>.json \
  --output-json reports/representative-technical-review-$DAY.json \
  --output-markdown reports/representative-technical-review-$DAY.md \
  --output-csv reports/representative-technical-review-$DAY.csv \
  --workers 8

# 2) 回撤 + 最优确定性条件
python3.12 analyze_edge_conditions.py \
  --seed reports/representative-technical-review-$DAY.json \
  --output reports/etf68-edge-conditions-$DAY.json \
  --workers 6

# 3) 画布数据/TSX 建好后归档
python3.12 save_snapshot.py --date $DAY \
  --canvas ~/.cursor/projects/Users-mac-Desktop-github-my-tool-project/canvases/etf-68-status-$DAY.canvas.tsx
```

npm 别名：`npm run report` / `npm run edge` / `npm run snapshot`（仍须显式传 dated 路径时用上面的 python 命令）。

## Agent 工作流

```
Task Progress:
- [ ] Step 1: 清代理，确定 DAY / PREV seed
- [ ] Step 2: generate_review → 校验 data_date==DAY 且 rows==68
- [ ] Step 3: analyze_edge_conditions → etf68-edge-conditions-$DAY.json
- [ ] Step 4: 组装 canvas-data（含 ret30/dd/bestEdge/中文板块）并写画布
- [ ] Step 5: save_snapshot.py --date $DAY
- [ ] Step 6: 简报状态分布 + 画布链接；飞书同步仅在用户明确要求时做
```

### Step 2 校验

读 `reports/representative-technical-review-$DAY.json`：

- `data_date` / 各行 `date` 必须等于 `DAY`
- `len(rows)==68`
- 失败则报错退出，不写画布

### Step 4 画布

1. **IDE 画布路径（必须）**  
   `~/.cursor/projects/Users-mac-Desktop-github-my-tool-project/canvases/etf-68-status-$DAY.canvas.tsx`  
   只从 `cursor/canvas` 导入；数据全部 inline；禁止 `fetch`。
2. **仓库副本**  
   `reports/etf-68-status-$DAY.canvas.tsx`  
   `reports/etf68-canvas-data-$DAY.json`
3. 可复用前一日画布 UI（筛选/排序/行色逻辑），替换 `DATA` 常量。
4. 行字段最少包含：

| 字段 | 来源 |
|------|------|
| action/trend/code/name/rsi/kdj/macd/sentiment* | review JSON |
| ret1/ret5/ret10/ret20 | review `ret*_pct` |
| ret30Hold / ret30Entry / ret30AsOf | 日线：`(close[-1]/close[-31]-1)*100`，entry=`bars[-31].date` |
| dd10/20/30/60/120, bestEdge | edge-conditions JSON |
| sector | 英文 key → 中文（见 [reference.md](reference.md)） |
| reportIndex | review 原序 |

5. 行背景优先级（与画布 `rowTone` 一致）：技术候选 → 不追涨 → 空头趋势 → 默认。
6. 「最优确定性条件」文案含义：历史同条件下前瞻 10 日收益均值保守下界（样本≥8）；须在 Callout 标明**非实盘保证**。

### Step 5 快照

目录：`reports/snapshots/$DAY/`  
含：`etf-68-status.canvas.tsx`、`canvas-data.json`、`edge-conditions.json`、`representative-technical-review.json`、`interactive-canvas.html`（若有）、`manifest.json`。

## 可选：飞书

仅当用户明确要求同步时：

1. 知识库 Tool 下多维表格（可筛选排序），**不要**只塞静态 Markdown 冒充画布。
2. 表名用 `$DAY`；板块中文；「行色」字段对齐画布优先级；建议用户在飞书开「按行色给记录上色」。
3. 勿提交 `_auth/` 授权二维码与 `_feishu_*` 临时文件。

## 回报格式

用中文简报：

- 数据日期 / 生成时间 / 宽度
- 状态计数（技术候选/观察/不追涨/暂缓）与趋势计数
- 30 日至今 Top 若干
- 画布路径 + `reports/snapshots/$DAY/`

## 附加资源

- 板块中文映射与文件命名：[reference.md](reference.md)
