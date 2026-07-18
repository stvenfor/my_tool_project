# A 股行业资金流向 TOP 5

Remotion 竖屏数据动画，固定展示 2026-07-17 同花顺行业资金流收盘快照。

## 数据口径

- 主源：同花顺行业资金流，经 AKShare `stock_fund_flow_industry(symbol="即时")` 获取。
- 净流入榜：`净额 > 0`，按源数据净额降序。
- 净流出榜：`净额 < 0`，按源数据净额升序。
- 单位：亿元。排序使用接口返回原始精度，画面显示两位小数。
- 东方财富行业板块资金流仅用于日期、方向和量级的辅助观察；分类口径不同，不参与合并或平均。
- AKShare 接口没有把该字段明确命名为“主力净额”，所以视频采用“行业净流入/净流出”标题。

字段映射：

| 成片字段 | AKShare / 同花顺字段 |
| --- | --- |
| `industry` | `行业` |
| `grossInflow` | `流入资金` |
| `grossOutflow` | `流出资金` |
| `netAmount` | `净额` |

## 使用

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm run typecheck
npm run build
npm run studio
npm run stills
npm run render
```

数据抓取脚本只允许在 2026-07-17 当天 15:05 后运行，防止“即时”接口在其他日期覆盖历史快照：

```bash
.venv/bin/python scripts/fetch_industry_flow.py
```

成片输出到 `out/a-share-industry-flow-2026-07-17-compatible.mp4`。视频使用标准
H.264 `yuv420p / bt709`，并移除空音轨，以兼容内嵌播放器。
