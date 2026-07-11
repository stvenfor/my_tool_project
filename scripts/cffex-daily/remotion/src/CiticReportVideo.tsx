import { AbsoluteFill, Audio, Img, interpolate, staticFile, useVideoConfig } from "remotion";
import { AnimatedBarChart } from "./AnimatedBarChart";
import { AnimatedNumber } from "./AnimatedNumber";
import {
  SYMBOLS,
  SYMBOL_NAMES,
  THEME,
  DEFAULT_LOGO_HANDLE,
  DEFAULT_BGM_VOLUME,
  formatNetChange,
  formatSymbolValue,
  type ReportData,
} from "./types";
import { holdOrInterpolate, holdOrSpring, useAnimFrame, useIsHold } from "./useAnimFrame";

export type CiticReportVideoProps = {
  report: ReportData;
};

const CARD_STAGGER = 10;
const CARD_START = 24;
const CHART_START = 62;
const SUMMARY_START = 100;
const FOOTER_START = 128;

const SectionHead: React.FC<{
  num: string;
  title: string;
  subtitle: string;
  startFrame: number;
}> = ({ num, title, subtitle, startFrame }) => {
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
        alignItems: "baseline",
        gap: 10,
        opacity: entrance,
        transform: `translateX(${(1 - entrance) * -12}px)`,
      }}
    >
      <span
        style={{
          fontFamily: THEME.serif,
          fontSize: 22,
          fontWeight: 700,
          color: THEME.accentSoft,
          lineHeight: 1,
          letterSpacing: "-0.02em",
        }}
      >
        {num}
      </span>
      <div>
        <h2
          style={{
            fontFamily: THEME.serif,
            fontSize: 16,
            fontWeight: 700,
            color: THEME.ink,
            margin: 0,
            lineHeight: 1.3,
          }}
        >
          {title}
        </h2>
        <p
          style={{
            fontSize: 11,
            color: THEME.inkSecondary,
            margin: "3px 0 0",
            letterSpacing: "0.01em",
          }}
        >
          {subtitle}
        </p>
      </div>
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
        padding: "18px 16px 16px",
        borderRadius: 10,
        background: isLong
          ? `linear-gradient(145deg, #fff5f5 0%, ${THEME.longBg} 100%)`
          : `linear-gradient(145deg, #f0faf5 0%, ${THEME.shortBg} 100%)`,
        border: `1px solid ${isLong ? "rgba(209,77,77,0.35)" : "rgba(58,154,106,0.35)"}`,
        boxShadow: `0 6px 18px ${isLong ? THEME.longGlow : THEME.shortGlow}`,
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
      <span
        style={{
          position: "absolute",
          right: 8,
          top: 6,
          fontSize: 42,
          fontWeight: 800,
          opacity: 0.06,
          letterSpacing: "-0.04em",
        }}
      >
        {symbol}
      </span>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 10,
          position: "relative",
          zIndex: 1,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: THEME.inkSecondary }}>
          {symbol} · {SYMBOL_NAMES[symbol]}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            padding: "3px 8px",
            borderRadius: 999,
            background: isLong ? "rgba(209,77,77,0.18)" : "rgba(58,154,106,0.18)",
            color: isLong ? THEME.longDeep : THEME.shortDeep,
          }}
        >
          {badge}
        </span>
      </div>
      <div
        style={{
          fontSize: 30,
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
      <div style={{ fontSize: 11, marginTop: 8, color: THEME.inkSecondary, position: "relative", zIndex: 1 }}>
        <AnimatedNumber
          value={Math.abs(net)}
          startFrame={delay + 8}
          durationFrames={28}
          formatter={(v) => formatNetChange(isLong ? Math.round(v) : -Math.round(v))}
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
}> = ({ label, value, unit, index, colored, hero }) => {
  const animFrame = useAnimFrame();
  const isHold = useIsHold();
  const { fps } = useVideoConfig();
  const delay = SUMMARY_START + index * 8;
  const entrance = holdOrSpring(isHold, animFrame, fps, delay, {
    damping: 18,
    stiffness: 130,
  });
  const isLong = value >= 0;

  return (
    <div
      style={{
        padding: "18px 14px",
        background: hero ? `linear-gradient(160deg, ${THEME.longBg} 0%, #fff5f5 85%)` : THEME.bg,
        borderRight: index < 2 ? `1px solid ${hero ? "rgba(209,77,77,0.3)" : THEME.line}` : "none",
        opacity: entrance,
        transform: `translateY(${(1 - entrance) * 12}px)`,
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: THEME.inkSecondary,
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: hero ? 28 : 22,
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          color: colored ? (isLong ? THEME.longDeep : THEME.shortDeep) : THEME.ink,
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
              : Math.round(v).toLocaleString("zh-CN")
          }
        />
      </div>
      <div style={{ fontSize: 11, color: THEME.inkSecondary, marginTop: 6 }}>{unit}</div>
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

  const chartOpacity = holdOrInterpolate(isHold, animFrame, [CHART_START, CHART_START + 12], [0, 1]);

  const footerOpacity = holdOrInterpolate(isHold, animFrame, [FOOTER_START, FOOTER_START + 18], [0, 1]);
  const logoHandle = report.logo_handle ?? DEFAULT_LOGO_HANDLE;
  const bgmVolume = report.bgm_volume ?? DEFAULT_BGM_VOLUME;

  return (
    <AbsoluteFill
      style={{
        fontFamily: THEME.sans,
        background: THEME.bg,
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
          padding: "40px 32px 28px",
          overflow: "hidden",
        }}
      >
        <header
          style={{
            flexShrink: 0,
            marginBottom: 28,
            borderBottom: `2px solid ${THEME.ink}`,
            paddingBottom: 18,
            opacity: headerEntrance,
            transform: `translateY(${(1 - headerEntrance) * -12}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 16,
              marginBottom: 12,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontFamily: THEME.serif,
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                  color: THEME.accent,
                }}
              >
                中信期货 · 净持仓日报
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0 }}>
              <Img
                src={staticFile("logo.png")}
                style={{ width: 60, height: 60, objectFit: "contain" }}
              />
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 600,
                  color: THEME.inkSecondary,
                  letterSpacing: "0.01em",
                  whiteSpace: "nowrap",
                  lineHeight: 1.2,
                }}
              >
                {logoHandle}
              </span>
            </div>
          </div>
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
            margin: "0 0 22px 0",
            padding: "14px 16px 14px 20px",
            background: `linear-gradient(90deg, ${THEME.longBg} 0%, ${THEME.bg} 72%)`,
            borderLeft: `3px solid ${THEME.long}`,
            borderRadius: "0 8px 8px 0",
            opacity: quoteOpacity,
          }}
        >
          <p
            style={{
              fontFamily: THEME.serif,
              fontSize: 15,
              lineHeight: 1.65,
              color: THEME.ink,
              fontStyle: "italic",
              margin: 0,
            }}
          >
            {report.daily_quote}
          </p>
        </blockquote>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 20, minHeight: 0 }}>
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
                gridTemplateColumns: "repeat(2, 1fr)",
                gap: 10,
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

          <section style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <SectionHead
              num="02"
              title="持仓变化对比"
              subtitle="各品种净加减仓手数（正为加多，负为加空）· 来源于网络"
              startFrame={48}
            />
            <div
              style={{
                flex: 1,
                minHeight: 240,
                opacity: chartOpacity,
                background: THEME.panel,
                border: `1px solid ${THEME.line}`,
                borderRadius: 12,
                padding: "14px 12px 8px",
                boxShadow: "0 4px 20px rgba(26,26,26,0.04)",
              }}
            >
              <AnimatedBarChart data={report.citic_by_symbol} startFrame={CHART_START + 5} />
            </div>
          </section>

          <section style={{ flexShrink: 0 }}>
            <SectionHead
              num="03"
              title="市场概览"
              subtitle="全市场机构持仓汇总 · 来源于网络"
              startFrame={88}
            />
            <div
              style={{
                borderRadius: 12,
                overflow: "hidden",
                border: `1px solid ${THEME.line}`,
                boxShadow: "0 4px 20px rgba(26,26,26,0.04)",
              }}
            >
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1.15fr 1fr 1fr",
                }}
              >
              <SummaryItem
                label="中信整体"
                value={report.citic_total}
                unit="净持仓变化"
                index={0}
                colored
                hero
              />
              <SummaryItem
                label="前20机构净空单"
                value={report.top20_net_short_total}
                unit="手"
                index={1}
              />
              <SummaryItem
                label="今日净买入"
                value={report.net_buy_total}
                unit="手"
                index={2}
              />
              </div>
            </div>
          </section>
        </div>

        <footer
          style={{
            flexShrink: 0,
            marginTop: 24,
            paddingTop: 16,
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
