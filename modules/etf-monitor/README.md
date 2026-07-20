# ETF Monitor

本模块对审阅过的 ETF 池做静态审计、真实成交记账、高置信度扫描和持仓风险提醒。它只提供决策支持：没有券商连接，不会创建、提交或撤销订单。所有命令向 stdout 输出一个稳定的 JSON 对象；键按字典序序列化，`schema_version` 当前为 `1`。

## 快速使用

从仓库根目录运行：

```bash
npm run etf:audit
npm run etf:scan -- --code 512890 --fixture modules/etf-monitor/state/provider.json
npm run etf:scheduled-check -- --fixture modules/etf-monitor/state/provider.json
```

`audit` 汇总 107 条审阅记录、106 只可交易 ETF、13 个完全重复组，并明确排除指数 `883432`。`scan` 必须使用 `--code CODE`（可重复）；`scheduled-check` 未给 `--code` 时扫描每个 sector × market 桶内通过静态流动性门槛的确定性首选 ETF。

## 真实成交输入

只在券商已经成交后记账，格式必须是：

```text
record-buy CODE --price ACTUAL_PRICE (--shares ACTUAL_SHARES | --amount ACTUAL_FILL_AMOUNT_CNY) [--confirm-second-tranche]
record-sell CODE --price ACTUAL_PRICE (--shares ACTUAL_SHARES | --amount ACTUAL_FILL_AMOUNT_CNY)
```

示例：

```bash
npm run etf:record-buy -- 512890 --price 1.234 --shares 8100
npm run etf:record-buy -- 512890 --price 1.210 --amount 9801 --confirm-second-tranche
npm run etf:record-sell -- 512890 --price 1.300 --shares 4000
```

- `--price` 是券商回报的实际成交单价。
- `--shares` 是实际成交份额；`--amount` 是实际成交金额，程序按 `amount / price` 换算份额。两者必须且只能提供一个。
- 金额按分、份额按 8 位小数存储。佣金、税费等没有单独建模；若它们需要进入成本，请以券商最终成交回报为准并保持输入口径一致。
- `--confirm-second-tranche` 是一次显式确认：第二次建仓前已经重新核对技术条件、权威一级催化与独立确认、组合回撤限制，以及券商实时价和溢折价。价格下跌本身绝不构成加仓许可。

运行时组合状态只写入 `modules/etf-monitor/state/portfolio.json`，采用临时文件加原子替换；整个 `state/` 目录被 Git 忽略。仓库只提交无持仓示例 `state.example.json`。不要把真实账户信息、凭据或券商导出文件写入仓库。

持久化组合状态使用 `schema_version` 2（与命令输出 envelope 的版本分开）。读取和写入都会校验完整 schema、有限数值、金额精度与组合不变量；旧版、缺字段、额外字段、`NaN`/无穷值或自相矛盾的状态都会返回固定 JSON `INPUT_ERROR`，不会带 traceback，也不会覆盖原状态。

## JSON 状态

所有结果都有：

```json
{"advisory_only":true,"command":"scan","orders_placed":false,"reasons":[],"schema_version":1,"status":"NO_ACTION"}
```

命令特有字段保持固定：

- `audit`: `record_count`、`tradable_count`、`exact_duplicate_group_count`、`excluded_codes`、`reports`。
- `record-buy` / `record-sell`: `code`、成交后的 `position`（完全平仓为 `null`）和完整 `state`。
- `scan`: `source_timestamp` 和逐 ETF 的 `results`；每项含 `risk_controls`。
- `scheduled-check`: `source_timestamp`、已去重的 `alerts` 与 `scan_results`；每项扫描还含 `portfolio_gate`，每条告警自带它自己的 `source_timestamp` 和 `risk_controls`（-3%/信号失效、二次确认、券商复核等）。

即使命令失败，命令特有字段仍存在并使用空值：scan 保留 `source_timestamp/results`，scheduled-check 保留 `source_timestamp/alerts/scan_results`，record 命令保留可为 `null` 的 `code/position/state`，audit 保留其五个汇总字段。因此自动化只需解析一个固定 JSON 文档。

`scheduled-check` 顶层 `status` 只会是：

- `NO_ACTION`：无信号或已确认休市；
- `BUY_CANDIDATE_NEEDS_CATALYST`：全部数值门槛已通过，但权威一级催化或独立确认尚未完成；
- `BUY_CANDIDATE`：数值门槛及两级催化确认全部通过，仍只是人工复核候选；
- `POSITION_ALERT`：出现 +4.5%、+5%、-3%/信号失效或组合回撤提醒；
- `DATA_ERROR`：数据缺失、过期、冲突，或实时 provider 依赖不完整；
- `INPUT_ERROR`：命令、成交或状态输入无效。

同一持仓周期的 +4.5%、+5%、止损和风险退出标志会持久化，因此重复执行不会重复提醒。完全平仓后重新建仓会开始新的持仓周期。每条持仓 alert 保留该持仓行情自己的时间戳，不用其他代码较早的时间覆盖。任何结果均含 `orders_placed: false`。

`scheduled-check` 会先完成交易日历核验。确认休市时立即返回 `NO_ACTION`，不读取持仓行情、不扫描候选，也不修改状态；日历缺失、过期、冲突或结构无效时立即返回 `DATA_ERROR`，同样不执行后续步骤或修改状态。只有明确确认开市后才处理持仓和候选。候选催化缺失不会屏蔽已有持仓的价格或风险告警。

## 离线 fixture / provider 协议

测试和无网络运行使用 `--fixture FILE`。JSON 顶层字段为：

```json
{
  "as_of": "2026-07-20T14:45:00+08:00",
  "current_quotes": [],
  "daily_bars": [],
  "aum": {},
  "premium": {},
  "benchmark_bars": [],
  "calendar": {},
  "catalyst": {}
}
```

单标运行且恰好只涉及一个选中代码时，上述数据字段可直接承载该标的数据。多标 fixture 不允许复用单份 payload：`current_quotes`、`daily_bars`、`aum`、`premium`、`catalyst` 必须按 ETF code 映射，`benchmark_bars` 必须按每条 universe 记录的 tracking-index / benchmark key 映射。若 scheduled-check 的现有持仓与选中代码合计涉及多只 ETF，`current_quotes` 同样必须逐 code 映射。缺映射或缺 key 返回 `DATA_ERROR`，绝不静默把一只 ETF 的数据用于另一只。

`as_of`、所有 `timestamp` 必须是带时区 ISO 8601；`date`、`session_date` 使用 `YYYY-MM-DD`。fixture 必须包含相互独立的现价来源、至少 61 根 ETF 日线、benchmark 日线、AUM、溢折价、权威交易日历和催化确认。

## 数据与风险边界

默认 public 模式只有公开行情端点适配器，不内置权威交易日历、催化来源或 tracking-index → benchmark code 映射。CLI 在这些依赖未显式提供时返回 `DATA_ERROR`，不会用周一至周五猜交易日、把新闻搜索当一级来源，或把 tracking-index 文本猜成行情代码。公开端点可能延迟、变更、限流或互相冲突。

初始资金假设为 CNY 100,000，其中风险资产最多 CNY 40,000、保留现金 CNY 60,000；这笔现金是每次买入后都必须满足的硬底线，而非初始配置提示。目标单笔为 CNY 10,000，实际单笔成交金额最多 CNY 11,000；额外 10% 仅用于整手/成交容差，不把目标仓位提高到 CNY 11,000。最多两只 ETF，每只最多两笔、成本最多 CNY 20,000。scheduled-check 在技术/催化扫描后用更新后的组合状态计算 `portfolio_gate`；回撤 >=1.5%、冷静期未结束、`valuation_required`、`risk_reset_pending`、买入后现金低于状态中的硬底线、持仓数/总风险敞口/单笔/单 ETF 成本/两笔上限任一不满足时，顶层不得是 `BUY_CANDIDATE` 或 `BUY_CANDIDATE_NEEDS_CATALYST`，而是 `NO_ACTION` 并给出稳定门控原因。

已有一笔的 ETF 即使通过门控，`portfolio_gate.requires_renewed_confirmation` 仍为 true，并给出 `second_tranche_requires_renewed_confirmation`；这只是提示仍需人工 renewed confirmation，不代表自动许可。实际记账依然必须显式传 `--confirm-second-tranche`。

组合高水位回撤 2% 触发风险退出提醒并开始 10 个已确认交易日冷静期。风险周期只有在冷静期结束且全部持仓已经关闭后才清除 `risk_reset_pending`；清除前禁止新买入。部分卖出，或多持仓组合中只平掉其中一只，会设置 `valuation_required` 并暂停买入；后续已确认开市的 scheduled-check 必须取得所有剩余持仓的完整、同期估值，才能重新计算权益并解除估值阻断。scheduled-check 先独立核验权威交易日历：仅 `is_trading_session=true` 且 session date 与上海当日一致时递减，同一交易日只递减一次；休市、过期或冲突日历不递减。行情或催化的其他错误不会阻止一个已经权威确认的交易日递减。完整数值门槛见 `src/scanner.py`，持仓规则见 `src/portfolio.py`。

## 持仓信号失效输入

`--invalidated-code CODE` 只用于已经持有、且由可靠、及时、相互一致的数据明确确认信号失效的代码，可重复传入。可接受的依据包括收盘跌破 MA20 或 MA60、MA20 转为下行、20日相对强度不再为正，或权威不利事件/核心催化反转；这里没有 MA60 斜率门槛。数据有歧义、过期、缺失或冲突时不得传入该参数，也不得把不确定性解释成失效。

确认失效时，为每个对应持仓追加 `--invalidated-code CODE`，并记录代码、可靠来源、判定依据、事件时间和数据时间。该输入会进入持仓周期的一次性 -3%/信号失效提醒；它是人工确认的风险输入，不是卖单，也不会触发自动交易。

在人工决策或操作前，必须在券商终端再次核对可交易状态、实时价、买卖盘、溢折价、份额与实际成交金额；同时核对输出的 `source_timestamp`、风险字段和失效条件。程序输出不是收益保证，也不替代券商成交回报或适合性判断。

定时任务合同见 [automation-prompt.md](automation-prompt.md)。
