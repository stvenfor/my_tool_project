# etf-68-daily reference

## 文件命名

| 产物 | 路径 |
|------|------|
| 技术面报告 | `modules/etf-monitor/reports/representative-technical-review-$DAY.{json,md,csv}` |
| 画布数据 | `modules/etf-monitor/reports/etf68-canvas-data-$DAY.json` |
| 回撤/确定性 | `modules/etf-monitor/reports/etf68-edge-conditions-$DAY.json` |
| 仓库画布副本 | `modules/etf-monitor/reports/etf-68-status-$DAY.canvas.tsx` |
| IDE 画布 | `~/.cursor/projects/Users-mac-Desktop-github-my-tool-project/canvases/etf-68-status-$DAY.canvas.tsx` |
| 交互 HTML | `modules/etf-monitor/reports/etf68-interactive-canvas.html`（及可选 `-$DAY.html`） |
| 日快照 | `modules/etf-monitor/reports/snapshots/$DAY/` |

Seed：取 `reports/representative-technical-review-*.json` 中最新且 `data_date < DAY` 的一份。

## 板块中文

```
advanced_equipment 高端装备 | agriculture 农业 | agriculture_commodity 农产品
artificial_intelligence 人工智能 | bank 银行 | battery 电池
biotechnology 生物科技 | broad_market 宽基 | broad_tech 科技宽基
building_materials 建材 | cashflow_factor 现金流因子 | coal 煤炭
commodity_equity 商品股 | communication 通信 | consumer 消费
consumer_electronics 消费电子 | convertible_bond 可转债 | credit_bond 信用债
defense 军工 | dividend_factor 红利 | education 教育
electric_utility 电力公用 | electronics 电子 | energy 能源
energy_chemical 能源化工 | food_beverage 食品饮料 | gaming 游戏
gold 黄金 | government_bond 国债 | growth_board 创业板
healthcare 医药 | infrastructure 基建 | innovative_drug 创新药
intelligent_manufacturing 智能制造 | internet 互联网 | large_cap 大盘
liquor 白酒 | livestock 畜牧 | machinery 机械 | media 传媒
mid_cap 中盘 | mid_cap_factor 中盘因子 | new_energy 新能源
new_energy_vehicle 新能源汽车 | new_materials 新材料 | nonferrous_metals 有色金属
oil_gas 油气 | rare_earth 稀土 | real_estate 房地产 | robotics 机器人
satellite 卫星 | securities 证券 | securities_insurance 证券保险
semiconductor 半导体 | small_cap 小盘 | smart_driving 智能驾驶
software 软件 | solar 光伏 | star_50 科创50
state_owned_enterprise 国企 | steel 钢铁 | technology 科技
```

未列出的 key 原样保留，并在回报中提示补映射。

## 关键脚本

| 脚本 | 作用 |
|------|------|
| `generate_review.py` | 拉日线+份额，写 dated review |
| `analyze_edge_conditions.py` | 多窗口回撤 + 最优确定性条件（结束时可自动 snapshot，仍建议显式再跑一次确保画布已更新） |
| `save_snapshot.py` | 归档画布/JSON 到 `snapshots/$DAY` |

## 确定性条件口径

- 回撤窗：10/20/30/60/120 交易日 peak→close
- 前瞻：此后 10 个交易日收益
- 得分：`mean - std/sqrt(n)`，`n>=8`
- 列展示示例：`近120日深回撤(8-15%)+趋势空头｜样本10｜胜率100%｜此后10日均+4.24%｜确定性+3.71%`
