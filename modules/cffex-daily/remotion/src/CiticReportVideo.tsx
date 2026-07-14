import { AbsoluteFill, Audio, Img, interpolate, staticFile, useVideoConfig } from "remotion";
import { AnimatedBarChart } from "./AnimatedBarChart";
import { AnimatedNumber } from "./AnimatedNumber";
import {
  SYMBOLS,
  SYMBOL_NAMES,
  THEME,
  DEFAULT_LOGO_HANDLE,
  DEFAULT_BGM_VOLUME,
  formatStockValue,
  formatSymbolValue,
  type ReportData,
  type SymbolCode,
} from "./types";
import { holdOrInterpolate, holdOrSpring, useAnimFrame, useIsHold } from "./useAnimFrame";

export type CiticReportVideoProps = {
  report: ReportData;
};

const CARD_STAGGER = 8;
const CARD_START = 24;
const CHART_START = 58;
const SUMMARY_START = 96;
const FOOTER_START = 124;

function maxChangeSymbol(data: Record<SymbolCode, number>): SymbolCode {
  return SYMBOLS.reduce((best, symbol) =>
    Math.abs(data[symbol]) > Math.abs(data[best]) ? symbol : best,
  );
}

const ChartLegend: React.FC = () => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      fontSize: 10,
      fontWeight: 600,
      color: THEME.inkSecondary,
      flexShrink: 0,
      whiteSpace: "nowrap",
    }}
  >
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: THEME.long }} />
      加多
    </span>
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: THEME.short }} />
      加空
    </span>
  </div>
);

const SectionHead: React.FC<{
  num: string;
  title: string;
  subtitle?: string;
  startFrame: number;
  legend?: boolean;
}> = ({ num, title, subtitle, startFrame, legend }) => {
  const animFrame = useAnimFrame();
  const isHold = useIsHold();
  const { fps } = useVideoConfig();
  const entrance = holdOrSpring(isHold, animFrame, fps, startFrame, {
    damping: 20,
    stiffness: 120,
  });

  return (
    <div
      style={{
        marginBottom: 12,
        display: "flex",
        alignItems: legend ? "center" : "baseline",
        gap: 12,
        opacity: entrance,
        transform: `translateX(${(1 - entrance) * -12}px)`,
      }}
    >
      <span
        style={{
          fontSize: 12,
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          color: THEME.accentSoft,
          lineHeight: 1,
          letterSpacing: "0.04em",
        }}
      >
        {num}
      </span>
      <div style={{ flex: legend ? 1 : undefined, minWidth: 0 }}>
        <h2
          style={{
            fontSize: 16,
            fontWeight: 700,
            color: THEME.ink,
            margin: 0,
            lineHeight: 1.3,
          }}
        >
          {title}
        </h2>
        {subtitle ? (
          <p
            style={{
              fontSize: 12,
              color: THEME.inkSecondary,
              margin: "3px 0 0",
              letterSpacing: "0.01em",
            }}
          >
            {subtitle}
          </p>
        ) : null}
      </div>
      {legend ? <ChartLegend /> : null}
    </div>
  );
};

const SymbolCell: React.FC<{
  symbol: (typeof SYMBOLS)[number];
  net: number;
  index: number;
}> = ({ symbol, net, index }) => {
  const animFrame = useAnimFrame();
  const isHold = useIsHold();
  const { fps } = useVideoConfig();
  const delay = CARD_START + index * CARD_STAGGER;
  const entrance = holdOrSpring(isHold, animFrame, fps, delay, {
    damping: 18,
    stiffness: 130,
  });
  const isLong = net >= 0;
  const badge = isLong ? "↑ 加多" : "↓ 加空";

  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        padding: "12px 10px 10px",
        borderRadius: 12,
        background: isLong
          ? `linear-gradient(155deg, #ffffff 0%, ${THEME.longBg} 100%)`
          : `linear-gradient(155deg, #ffffff 0%, ${THEME.shortBg} 100%)`,
        border: `1px solid ${isLong ? "rgba(224,69,69,0.28)" : "rgba(47,155,106,0.28)"}`,
        boxShadow: isLong
          ? `0 6px 18px ${THEME.longGlow}, inset 0 1px 0 rgba(255,255,255,0.9)`
          : `0 6px 18px ${THEME.shortGlow}, inset 0 1px 0 rgba(255,255,255,0.9)`,
        textAlign: "left",
        opacity: entrance,
        transform: `translateY(${(1 - entrance) * 16}px)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 4,
          background: isLong
            ? `linear-gradient(180deg, ${THEME.long} 0%, ${THEME.longDeep} 100%)`
            : `linear-gradient(180deg, ${THEME.short} 0%, ${THEME.shortDeep} 100%)`,
        }}
      />
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 4,
          marginBottom: 8,
          position: "relative",
          zIndex: 1,
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: THEME.inkSecondary,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {symbol}·{SYMBOL_NAMES[symbol]}
        </span>
        <span
          style={{
            alignSelf: "flex-start",
            fontSize: 10,
            fontWeight: 700,
            padding: "2px 6px",
            borderRadius: 999,
            background: isLong ? "rgba(224,69,69,0.16)" : "rgba(47,155,106,0.16)",
            color: isLong ? THEME.longDeep : THEME.shortDeep,
            border: `1px solid ${isLong ? "rgba(224,69,69,0.2)" : "rgba(47,155,106,0.2)"}`,
          }}
        >
          {badge}
        </span>
      </div>
      <div
        style={{
          fontSize: 28,
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "-0.04em",
          lineHeight: 1,
          color: isLong ? THEME.longDeep : THEME.shortDeep,
          position: "relative",
          zIndex: 1,
        }}
      >
        <AnimatedNumber
          value={net}
          startFrame={delay + 8}
          durationFrames={28}
          formatter={(v) => formatSymbolValue(Math.round(v))}
        />
      </div>
    </div>
  );
};

const SummaryItem: React.FC<{
  label: string;
  value: number;
  unit: string;
  index: number;
  colored?: boolean;
  hero?: boolean;
  stock?: boolean;
}> = ({ label, value, unit, index, colored, hero, stock }) => {
  const animFrame = useAnimFrame();
  const isHold = useIsHold();
  const { fps } = useVideoConfig();
  const delay = SUMMARY_START + index * 8;
  const entrance = holdOrSpring(isHold, animFrame, fps, delay, {
    damping: 18,
    stiffness: 130,
  });
  const isLong = value >= 0;
  const leftBar = hero
    ? `linear-gradient(180deg, ${THEME.long} 0%, ${THEME.longDeep} 100%)`
    : `linear-gradient(180deg, ${THEME.accentSoft} 0%, ${THEME.line} 100%)`;

  return (
    <div
      style={{
        position: "relative",
        padding: "16px 14px 14px 18px",
        borderRadius: 14,
        background: hero
          ? `linear-gradient(165deg, #fff8f8 0%, ${THEME.longBg} 55%, #ffffff 100%)`
          : "linear-gradient(165deg, #ffffff 0%, #fafafa 100%)",
        border: hero ? "1px solid rgba(224,69,69,0.22)" : "1px solid #ece8e3",
        boxShadow: hero
          ? "0 10px 28px rgba(224,69,69,0.12), inset 0 1px 0 rgba(255,255,255,0.95)"
          : "0 8px 22px rgba(20,20,20,0.06), inset 0 1px 0 rgba(255,255,255,0.95)",
        overflow: "hidden",
        opacity: entrance,
        transform: `translateY(${(1 - entrance) * 12}px)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 4,
          background: leftBar,
        }}
      />
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.06em",
          color: THEME.inkSecondary,
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: hero ? 30 : stock ? 20 : 24,
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          color: colored ? (isLong ? THEME.longDeep : THEME.shortDeep) : stock ? THEME.inkSecondary : THEME.ink,
          lineHeight: 1.05,
          letterSpacing: "-0.03em",
        }}
      >
        <AnimatedNumber
          value={value}
          startFrame={delay + 6}
          durationFrames={32}
          formatter={(v) =>
            colored
              ? formatSymbolValue(Math.round(v))
              : stock
                ? formatStockValue(Math.round(v))
                : Math.round(v).toLocaleString("zh-CN")
          }
        />
      </div>
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: THEME.inkMuted,
          marginTop: 6,
          letterSpacing: "0.02em",
        }}
      >
        {unit}
      </div>
    </div>
  );
};

export const CiticReportVideo: React.FC<CiticReportVideoProps> = ({ report }) => {
  const animFrame = useAnimFrame();
  const isHold = useIsHold();
  const { fps } = useVideoConfig();

  const headerEntrance = holdOrSpring(isHold, animFrame, fps, 0, {
    damping: 22,
    stiffness: 100,
  });

  const quoteOpacity = holdOrInterpolate(isHold, animFrame, [10, 22], [0, 1]);
  const highlightOpacity = holdOrInterpolate(isHold, animFrame, [18, 28], [0, 1]);
  const chartOpacity = holdOrInterpolate(isHold, animFrame, [CHART_START, CHART_START + 12], [0, 1]);
  const footerOpacity = holdOrInterpolate(isHold, animFrame, [FOOTER_START, FOOTER_START + 18], [0, 1]);
  const logoHandle = report.logo_handle ?? DEFAULT_LOGO_HANDLE;
  const bgmVolume = report.bgm_volume ?? DEFAULT_BGM_VOLUME;
  const peakSymbol = maxChangeSymbol(report.citic_by_symbol);
  const peakNet = report.citic_by_symbol[peakSymbol];
  const peakDir = peakNet >= 0 ? "加多" : "加空";

  return (
    <AbsoluteFill
      style={{
        fontFamily: THEME.sans,
        background: "linear-gradient(180deg, #ffffff 0%, #fafafa 100%)",
        color: THEME.ink,
      }}
    >
      {report.bgm_enabled !== false && (
        <Audio
          src={staticFile("bgm.mp3")}
          volume={(f) =>
            interpolate(f, [0, fps * 0.8], [0, bgmVolume], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          }
          loop
        />
      )}
      <div
        style={{
          width: 720,
          height: 1280,
          display: "flex",
          flexDirection: "column",
          padding: "36px 32px 28px",
          overflow: "hidden",
        }}
      >
        <header
          style={{
            flexShrink: 0,
            marginBottom: 22,
            borderBottom: `2px solid ${THEME.ink}`,
            paddingBottom: 16,
            opacity: headerEntrance,
            transform: `translateY(${(1 - headerEntrance) * -12}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              marginBottom: 10,
            }}
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: "0.08em",
                color: THEME.accent,
                padding: "5px 12px",
                borderRadius: 999,
                background: "rgba(61,74,92,0.07)",
                border: "1px solid rgba(61,74,92,0.12)",
              }}
            >
              中信期货 · 净持仓日报
            </span>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: THEME.accent,
                letterSpacing: "0.02em",
                whiteSpace: "nowrap",
              }}
            >
              {logoHandle}
            </span>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 16,
            }}
          >
            <h1
              style={{
                fontFamily: THEME.serif,
                fontSize: 26,
                fontWeight: 700,
                lineHeight: 1.25,
                color: THEME.ink,
                margin: 0,
                letterSpacing: "-0.01em",
                maxWidth: 520,
              }}
            >
              {report.date_label}
            </h1>
            <div style={{ flexShrink: 0, marginTop: 6 }}>
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: 18,
                  background: THEME.logoBg,
                  boxShadow: THEME.logoShadow,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px solid rgba(255,255,255,0.8)",
                }}
              >
                <Img
                  src={staticFile("logo.png")}
                  style={{
                    width: 46,
                    height: 46,
                    objectFit: "contain",
                    filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.08))",
                  }}
                />
              </div>
            </div>
          </div>
          <p
            style={{
              marginTop: 8,
              fontSize: 12,
              color: THEME.inkSecondary,
              letterSpacing: "0.02em",
            }}
          >
            来源于网络 · 机构持仓数据
          </p>
        </header>

        <blockquote
          style={{
            flexShrink: 0,
            margin: "0 0 18px 0",
            padding: "10px 14px",
            background: "rgba(61,74,92,0.04)",
            borderLeft: `3px solid ${THEME.accentSoft}`,
            borderRadius: "0 8px 8px 0",
            opacity: quoteOpacity,
          }}
        >
          <p
            style={{
              fontSize: 12,
              lineHeight: 1.45,
              color: THEME.inkSecondary,
              fontStyle: "normal",
              margin: 0,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {report.daily_quote}
          </p>
        </blockquote>

        <div
          style={{
            flexShrink: 0,
            marginBottom: 16,
            padding: "8px 12px",
            borderRadius: 8,
            background: `linear-gradient(90deg, ${THEME.longBg} 0%, rgba(255,240,240,0.2) 100%)`,
            border: "1px solid rgba(224,69,69,0.18)",
            fontSize: 12,
            fontWeight: 700,
            color: THEME.longDeep,
            letterSpacing: "0.02em",
            opacity: highlightOpacity,
          }}
        >
          今日要点 · {peakSymbol} {peakDir} {Math.abs(peakNet).toLocaleString("zh-CN")} 手为最大边际变化
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 20, minHeight: 0, overflow: "hidden" }}>
          <section style={{ flexShrink: 0 }}>
            <SectionHead
              num="01"
              title="各品种净持仓"
              subtitle="今日四大股指期货品种净加减仓 · 来源于网络"
              startFrame={14}
            />
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: 8,
              }}
            >
              {SYMBOLS.map((symbol, index) => (
                <SymbolCell
                  key={symbol}
                  symbol={symbol}
                  net={report.citic_by_symbol[symbol]}
                  index={index}
                />
              ))}
            </div>
          </section>

          <section style={{ flexShrink: 0, display: "flex", flexDirection: "column" }}>
            <SectionHead
              num="02"
              title="持仓变化对比"
              subtitle="平方根刻度 · 正为加多，负为加空"
              startFrame={44}
              legend
            />
            <div
              style={{
                flexShrink: 0,
                height: 332,
                width: "100%",
                opacity: chartOpacity,
              }}
            >
              <AnimatedBarChart data={report.citic_by_symbol} startFrame={CHART_START + 5} />
            </div>
          </section>

          <section style={{ flexShrink: 0 }}>
            <SectionHead num="03" title="市场概览" startFrame={84} />
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.15fr 1fr 1fr",
                gap: 12,
              }}
            >
              <SummaryItem
                label="中信整体"
                value={report.citic_total}
                unit="当日净持仓变化 · 手"
                index={0}
                colored
                hero
              />
              <SummaryItem
                label="前20机构净空单（存量）"
                value={report.top20_net_short_total}
                unit={`全市场存量 · ${report.top20_net_short_total.toLocaleString("zh-CN")} 手`}
                index={1}
                stock
              />
              <SummaryItem
                label="今日净买入"
                value={report.net_buy_total}
                unit="当日变动 · 手"
                index={2}
              />
            </div>
          </section>
        </div>

        <footer
          style={{
            flexShrink: 0,
            marginTop: 8,
            paddingTop: 12,
            borderTop: `1px solid ${THEME.line}`,
            opacity: footerOpacity,
          }}
        >
          <p
            style={{
              fontSize: 10,
              color: THEME.inkMuted,
              lineHeight: 1.8,
              letterSpacing: "0.02em",
              margin: 0,
            }}
          >
            数据来源于网络，仅供参考 · 投资有风险，入市需谨慎
          </p>
        </footer>
      </div>
    </AbsoluteFill>
  );
};
