# Codex ETF scheduled-check prompt

建议计划：仅中国交易日，在 `Asia/Shanghai` 约 `11:15` 与 `14:45` 各运行一次。以下正文用于 Codex 自动化任务：

```text
在仓库根目录执行 ETF advisory-only scheduled check。先用证券交易所正式交易日历确认今天是否为中国交易日；不要以工作日推测开市。若休市，输出 NO_ACTION 和核验来源后结束。

为审阅池中的候选与现有持仓准备完整、带时区的 provider JSON，并只写入被忽略的 modules/etf-monitor/state/。行情必须有两个独立来源且时间一致；同时取得至少 61 根 ETF 日线、明确映射的 benchmark 日线、AUM、溢折价和交易日历。涉及多只 ETF 时，current_quotes/daily_bars/AUM/premium/catalyst 必须按每只 ETF code 映射，benchmark_bars 与 benchmark_calendar 必须按明确的 benchmark key 映射；不得复用单标 payload。

对每个非 CN benchmark，必须从权威目标市场交易日历取得 `latest_completed_session_date`、`source` 和带时区的 `timestamp`，并确认日期与该 benchmark 最后一根日线一致。不得猜测缺失的上海 calendar、目标市场 benchmark_calendar、catalyst、benchmark mapping 或目标市场最新已完成交易日；缺失、过期、冲突、格式错误或未来日期一律按 DATA_ERROR 处理。CN benchmark 使用已核验的上海交易日历，无需单独目标市场日历。

催化必须先由权威一级来源确认，例如交易所/监管机构/政府部门正式公告、基金管理人正式公告或标的公司法定披露；再取得与一级来源相互独立的可靠来源确认。`catalyst` 必须包含 `primary_confirmed`、`corroborated`、`adverse`，以及 `primary_evidence` 和 `corroboration_evidence` 两个对象；每个 evidence 都必须写入非空的 `source`、`reference`、`event_timestamp`、`collected_at`。两套 source/reference 必须分别不同，四个时间必须带时区且距当前扫描时点不超过 24 小时；允许最多 1 分钟的时钟偏差，晚于扫描时点超过 1 分钟一律按 `DATA_ERROR` 处理，事件时间不得晚于采集时间。旧的共享 source/timestamp 格式禁止使用。搜索摘要、转述或单一媒体报道不能代替权威一级来源；来源不独立不能算独立确认。

只有明确确认开市后才继续。确认休市时立即以 NO_ACTION 结束，不读取持仓行情、不扫描候选、不修改状态；calendar 缺失、过期、冲突或无效时立即以 DATA_ERROR 结束，也不修改状态。候选 catalyst 缺失不得阻止已有持仓告警。

逐一核验现有持仓是否已经由可靠、及时且一致的数据确认失效。可接受依据包括收盘跌破 MA20 或 MA60、MA20 转为下行、20日相对强度不再为正，或权威不利事件/核心催化反转；不设置 MA60 斜率门槛。若数据有歧义、过期、缺失或冲突，不得将该代码标为失效。每个已确认失效的持仓都追加一个 `--invalidated-code CODE`，并记录代码、可靠来源、判定依据、事件时间与数据时间（依据与时间必须可审计）。

运行：npm run etf:scheduled-check -- --fixture modules/etf-monitor/state/provider.json [--invalidated-code CODE ...]

解析唯一 JSON 输出、每只候选的 `catalyst_provenance` 与 portfolio_gate。若组合回撤、冷静期、`valuation_required`、`risk_reset_pending`、买入后现金低于 CNY 60,000 硬底线、两只持仓、CNY 40,000 总敞口、CNY 11,000 单笔上限、单只 CNY 20,000 或两笔上限阻止买入，必须报告 NO_ACTION。1.5%-<2% 回撤只阻止新买入和加仓，不启动冷静期或重置高水位；只有回撤达到或超过 2% 才触发风险退出并启动 10 个已确认交易日冷静期。目标单笔仍为 CNY 10,000；额外 10% 仅是整手/成交容差。已有一笔时明确说明第二笔仍需人工 renewed confirmation，不能把候选当成自动许可。

无数据、数据过期、休市、来源冲突、无法明确 benchmark mapping，或催化缺少权威一级来源/独立确认时，一律无行动，不得推断补齐。权威确认的同一交易日冷静期只递减一次；休市不得递减。POSITION_ALERT、BUY_CANDIDATE_NEEDS_CATALYST 或 BUY_CANDIDATE 也只作为人工复核建议；绝不连接券商、创建订单或自动交易。对任何候选明确提醒用户在券商终端复核实时价、溢折价、份额/金额、风险与失效条件。

最后在 Codex 任务中给出简短结论：状态、代码、理由、source_timestamp、`catalyst_provenance` 中规范化后的 `primary` / `corroboration` 两套证据、风险/失效条件和 orders_placed=false。若没有行动，明确写“无行动”。
```
