import {z} from 'zod';

export const flowItemSchema = z.object({
  rank: z.number().int().min(1).max(5),
  industry: z.string().min(1),
  netAmount: z.number().finite(),
  grossInflow: z.number().finite().nonnegative(),
  grossOutflow: z.number().finite().nonnegative(),
});

export const rawRowSchema = z.object({
  sourceRank: z.number().int().positive(),
  industry: z.string().min(1),
  industryIndex: z.number().finite(),
  changePercent: z.number().finite(),
  grossInflow: z.number().finite().nonnegative(),
  grossOutflow: z.number().finite().nonnegative(),
  netAmount: z.number().finite(),
  companyCount: z.number().int().nonnegative(),
  leadingStock: z.string(),
  leadingStockChangePercent: z.number().finite(),
  currentPrice: z.number().finite().nonnegative(),
});

export const industryFlowDataSchema = z.object({
  tradeDate: z.literal('2026-07-17'),
  dataCutoff: z.literal('2026-07-17 15:00:00+08:00'),
  fetchedAt: z.string().datetime({offset: true}),
  timezone: z.literal('Asia/Shanghai'),
  source: z.string().min(1),
  sourceUrl: z.string().url(),
  secondaryCheckUrl: z.string().url(),
  unit: z.literal('亿元'),
  classification: z.string().min(1),
  akshareVersion: z.string().min(1),
  rawRowCount: z.literal(90),
  inflowTop5: z.array(flowItemSchema).length(5),
  outflowTop5: z.array(flowItemSchema).length(5),
  rawRows: z.array(rawRowSchema).length(90),
});

export type IndustryFlowData = z.infer<typeof industryFlowDataSchema>;

export const validateIndustryFlowData = (value: unknown): IndustryFlowData => {
  const data = industryFlowDataSchema.parse(value);
  const inflowNames = new Set(data.inflowTop5.map((item) => item.industry));
  const outflowNames = new Set(data.outflowTop5.map((item) => item.industry));

  if (inflowNames.size !== 5 || outflowNames.size !== 5) {
    throw new Error('资金流 TOP 5 包含重复行业');
  }
  if (!data.inflowTop5.every((item) => item.netAmount > 0)) {
    throw new Error('净流入榜包含非正数');
  }
  if (!data.outflowTop5.every((item) => item.netAmount < 0)) {
    throw new Error('净流出榜包含非负数');
  }

  const expectedInflow = [...data.inflowTop5].sort(
    (a, b) => b.netAmount - a.netAmount || a.industry.localeCompare(b.industry, 'zh-CN'),
  );
  const expectedOutflow = [...data.outflowTop5].sort(
    (a, b) => a.netAmount - b.netAmount || a.industry.localeCompare(b.industry, 'zh-CN'),
  );

  for (let index = 0; index < 5; index += 1) {
    if (data.inflowTop5[index].industry !== expectedInflow[index].industry) {
      throw new Error('净流入榜排序错误');
    }
    if (data.outflowTop5[index].industry !== expectedOutflow[index].industry) {
      throw new Error('净流出榜排序错误');
    }
  }

  return data;
};
