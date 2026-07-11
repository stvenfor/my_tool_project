import { Composition } from "remotion";
import { CiticReportVideo, type CiticReportVideoProps } from "./CiticReportVideo";
import { TOTAL_FRAMES } from "./constants";
import type { ReportData } from "./types";

const DEFAULT_REPORT: ReportData = {
  trade_date: "20260710",
  date_label: "2026年07月10日 周五",
  daily_quote: "方向对了，不怕路远，坚持就是胜利！",
  logo_handle: "@小水獭学AI",
  bgm_enabled: true,
  bgm_volume: 0.14,
  citic_by_symbol: { IH: 163, IF: -24, IC: 1510, IM: -126 },
  citic_total: 1523,
  top20_net_short_total: 136619,
  net_buy_total: 6193,
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="CiticReportVideo"
      component={CiticReportVideo}
      durationInFrames={TOTAL_FRAMES}
      fps={30}
      width={720}
      height={1280}
      defaultProps={{
        report: DEFAULT_REPORT,
      } satisfies CiticReportVideoProps}
    />
  );
};
