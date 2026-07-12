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
  ink: "#141414",
  inkSecondary: "#5c5c5c",
  inkMuted: "#8a8a8a",
  grid: "#d8d8d8",
  line: "#d0d0d0",
  long: "#e04545",
  longDeep: "#b82e2e",
  longBg: "#fff0f0",
  longGlow: "rgba(224, 69, 69, 0.32)",
  short: "#2f9b6a",
  shortDeep: "#1f7a52",
  shortBg: "#e8f8ef",
  shortGlow: "rgba(47, 155, 106, 0.28)",
  accent: "#3d4a5c",
  accentSoft: "#7a8a9c",
  panel: "#f7f5f2",
  panelDeep: "#ece8e3",
  bg: "#ffffff",
  logoBg: "linear-gradient(145deg, #ffffff 0%, #eef3fa 55%, #e3ebf5 100%)",
  logoShadow: "0 6px 16px rgba(61, 74, 92, 0.14), 0 2px 6px rgba(61, 74, 92, 0.08), inset 0 1px 0 rgba(255,255,255,0.95)",
  serif: 'Georgia, "Times New Roman", "Songti SC", serif',
  sans: '"Helvetica Neue", "PingFang SC", "Hiragino Sans GB", sans-serif',
} as const;

export function formatSymbolValue(net: number): string {
  const sign = net >= 0 ? "+" : "";
  return `${sign}${Math.round(net).toLocaleString("zh-CN")}`;
}

export function formatStockValue(n: number): string {
  const v = Math.round(n);
  if (Math.abs(v) >= 10000) {
    return `${(v / 10000).toFixed(1)}万`;
  }
  return v.toLocaleString("zh-CN");
}

export function formatNetChange(net: number): string {
  if (net >= 0) return `净加多 ${Math.abs(net).toLocaleString("zh-CN")}手`;
  return `净加空 ${Math.abs(net).toLocaleString("zh-CN")}手`;
}
