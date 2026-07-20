# Codex ETF scheduled-check prompt

建议计划：仅中国交易日，在 `Asia/Shanghai` 约 `11:15` 与 `14:45` 各运行一次。以下正文用于 Codex 自动化任务：

```text
在仓库根目录执行 ETF advisory-only scheduled check。先用证券交易所正式交易日历确认今天是否为中国交易日；不要以工作日推测开市。若休市，输出 NO_ACTION 和核验来源后结束。

为审阅池中的候选与现有持仓准备完整、带时区的 provider JSON，并只写入被忽略的 modules/etf-monitor/state/。行情必须有两个独立来源且时间一致；同时取得至少 61 根 ETF 日线、明确映射的 benchmark 日线、AUM、溢折价和交易日历。涉及多只 ETF 时，current_quotes/daily_bars/AUM/premium/catalyst 必须按每只 ETF code 映射，benchmark_bars 必须按明确的 benchmark key 映射；不得复用单标 payload。不得猜测缺失的 calendar、catalyst 或 benchmark mapping。

催化必须先由权威一级来源确认，例如交易所/监管机构/政府部门正式公告、基金管理人正式公告或标的公司法定披露；再取得与一级来源相互独立的可靠来源确认。记录来源、事件发生时间和数据时间。搜索摘要、转述或单一媒体报道不能代替权威一级来源；来源不独立不能算独立确认。

运行：npm run etf:scheduled-check -- --fixture modules/etf-monitor/state/provider.json

解析唯一 JSON 输出及每只候选的 portfolio_gate。若组合回撤、冷静期、两只持仓、CNY 40,000 总敞口、单只 CNY 20,000 或两笔上限阻止买入，必须报告 NO_ACTION。已有一笔时明确说明第二笔仍需人工 renewed confirmation，不能把候选当成自动许可。

无数据、数据过期、休市、来源冲突、无法明确 benchmark mapping，或催化缺少权威一级来源/独立确认时，一律无行动，不得推断补齐。权威确认的同一交易日冷静期只递减一次；休市不得递减。POSITION_ALERT、BUY_CANDIDATE_NEEDS_CATALYST 或 BUY_CANDIDATE 也只作为人工复核建议；绝不连接券商、创建订单或自动交易。对任何候选明确提醒用户在券商终端复核实时价、溢折价、份额/金额、风险与失效条件。

最后在 Codex 任务中给出简短结论：状态、代码、理由、source_timestamp、催化来源、风险/失效条件和 orders_placed=false。若没有行动，明确写“无行动”。
```
