# 批量话题生成报告

日期：2026-07-12

## 汇总

| 状态 | 数量 |
|------|------|
| 身份/关系话题总计 | 30 |
| 本批新增 | 14 |
| 校验失败 | 0 |

**10 类人群均已满 3 条话题。**

## 类别覆盖（每类 ≥3）

| 类别 | 话题数 | 话题 id |
|------|--------|---------|
| 打工人 | 3 | worker-overtime-burnout / moyu-economics / salary-silence |
| 家庭关系 | 3 | family-marriage-pressure / spring-festival / parent-control |
| 同学关系 | 3 | classmate-reunion-anxiety / borrow-money / lost-contact |
| 朋友关系 | 3 | friend-drifting-apart / negative-energy / plastic-friendship |
| 钓鱼人 | 3 | fishing-empty-handed / gear-upgrade / skip-work |
| 股市交易者 | 3 | stock-chase-highs / all-in / rumor-trade |
| 基金玩家 | 3 | fund-dca-faith / chase-hot / redeem-hesitate |
| 饭搭子 | 3 | mealbuddy-ghosting / menu-debate / aa-awkward |
| 酒友 | 3 | drinkbuddy-hangover / late-arrival / casual-gathering |
| 游戏队友 | 3 | gaming-blame-teammate / rank-anxiety / gacha-trap |

## 第三批新增（+14）

| 类别 | id | 角度 |
|------|-----|------|
| 同学关系 | classmate-lost-contact-2026 | 多年不联系 |
| 朋友关系 | friend-plastic-friendship-2026 | 塑料友情 |
| 钓鱼人 | fishing-gear-upgrade-2026 | 装备升级 |
| 钓鱼人 | fishing-skip-work-2026 | 钓鱼请假 |
| 股市交易者 | stock-all-in-2026 | 满仓梭哈 |
| 股市交易者 | stock-rumor-trade-2026 | 听消息炒股 |
| 基金玩家 | fund-chase-hot-2026 | 追涨基金 |
| 基金玩家 | fund-redeem-hesitate-2026 | 赎回犹豫 |
| 饭搭子 | mealbuddy-menu-debate-2026 | 选择困难 |
| 饭搭子 | mealbuddy-aa-awkward-2026 | AA尴尬 |
| 酒友 | drinkbuddy-late-arrival-2026 | 酒局迟到 |
| 酒友 | drinkbuddy-casual-gathering-2026 | 小酌聚会 |
| 游戏队友 | gaming-gacha-trap-2026 | 氪金陷阱 |

## 已避开敏感话题

- 无政治/宗教/性别对立
- 无婆媳翁婿等激烈家庭冲突
- 酒友聚焦聚会迟到、小酌、宿醉自嘲，非劝酒文化
- 股市/基金为韭菜自嘲，无具体标的推荐

## 下一步

```bash
# 审核单条
npm run infographic:approve -- --id classmate-lost-contact-2026

# 导入 Codex 出图
npm run infographic:one -- --id classmate-lost-contact-2026 --template-only
```
