export type SymbolCode = "IH" | "IF" | "IC" | "IM";

export type ReportData = {
  trade_date: string;
  date_label: string;
  daily_quote: string;
  logo_handle?: string;
  bgm_enabled?: boolean;
  bgm_volume?: number;
  citic_by_symbol: Record<SymbolCode, number>;
  citic_total: number;
  top20_net_short_total: number;
  net_buy_total: number;
};

export const SYMBOL_NAMES: Record<SymbolCode, string> = {
  IH: "上证50",
  IF: "沪深300",
  IC: "中证500",
  IM: "中证1000",
};

export const SYMBOLS: SymbolCode[] = ["IH", "IF", "IC", "IM"];

export const DEFAULT_LOGO_HANDLE = "@小水獭学AI";
export const DEFAULT_BGM_VOLUME = 0.14;

export const THEME = {
  ink: "#1a1a1a",
  inkSecondary: "#666666",
  inkMuted: "#999999",
  grid: "#e0e0e0",
  line: "#cccccc",
  long: "#d14d4d",
  longDeep: "#b83333",
  longBg: "#fde8e8",
  longGlow: "rgba(209, 77, 77, 0.28)",
  short: "#3a9a6a",
  shortDeep: "#257a52",
  shortBg: "#e2f4ea",
  shortGlow: "rgba(58, 154, 106, 0.28)",
  accent: "#4a5568",
  accentSoft: "#8b9aab",
  panel: "#f5f3f0",
  bg: "#ffffff",
  serif: 'Georgia, "Times New Roman", "Songti SC", serif',
  sans: '"Helvetica Neue", "PingFang SC", "Hiragino Sans GB", sans-serif',
} as const;

export function formatSymbolValue(net: number): string {
  const sign = net >= 0 ? "+" : "";
  return `${sign}${Math.round(net).toLocaleString("zh-CN")}`;
}

export function formatNetChange(net: number): string {
  if (net >= 0) return `净加多 ${Math.abs(net).toLocaleString("zh-CN")}手`;
  return `净加空 ${Math.abs(net).toLocaleString("zh-CN")}手`;
}
