import { interpolate, useVideoConfig } from "remotion";
import { SYMBOLS, SYMBOL_NAMES, THEME, type SymbolCode } from "./types";
import { holdOrInterpolate, holdOrSpring, useAnimFrame, useIsHold } from "./useAnimFrame";

type AnimatedBarChartProps = {
  data: Record<SymbolCode, number>;
  startFrame: number;
};

const WIDTH = 656;
const HEIGHT = 332;
const PAD_TOP = 24;
const PAD_BOTTOM = 48;
const PAD_X = 12;
const MIN_BAR = 14;

function barHeight(val: number, maxAbs: number, chartH: number): number {
  if (val === 0) return 0;
  const ratio = Math.sqrt(Math.abs(val) / maxAbs);
  return Math.max(MIN_BAR, ratio * (chartH / 2 - 30));
}

export const AnimatedBarChart: React.FC<AnimatedBarChartProps> = ({ data, startFrame }) => {
  const animFrame = useAnimFrame();
  const isHold = useIsHold();
  const { fps } = useVideoConfig();

  const values = SYMBOLS.map((s) => data[s]);
  const maxAbs = Math.max(...values.map(Math.abs), 1);
  const maxIdx = values.reduce((best, v, i) => (Math.abs(v) > Math.abs(values[best]) ? i : best), 0);
  const chartW = WIDTH - PAD_X * 2;
  const chartH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const zeroY = PAD_TOP + chartH / 2;
  const gap = chartW / SYMBOLS.length;
  const barW = gap * 0.42;
  const axisY = HEIGHT - PAD_BOTTOM + 16;

  const gridOpacity = holdOrInterpolate(isHold, animFrame, [startFrame, startFrame + 12], [0, 1]);

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} style={{ width: "100%", height: "100%" }}>
      <defs>
        <linearGradient id="gradLong" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f06a6a" />
          <stop offset="55%" stopColor={THEME.long} />
          <stop offset="100%" stopColor={THEME.longDeep} />
        </linearGradient>
        <linearGradient id="gradShort" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#56b888" />
          <stop offset="55%" stopColor={THEME.short} />
          <stop offset="100%" stopColor={THEME.shortDeep} />
        </linearGradient>
        <linearGradient id="zoneLong" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(224,69,69,0.10)" />
          <stop offset="100%" stopColor="rgba(224,69,69,0.03)" />
        </linearGradient>
        <linearGradient id="zoneShort" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(47,155,106,0.03)" />
          <stop offset="100%" stopColor="rgba(47,155,106,0.10)" />
        </linearGradient>
        <filter id="barShadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="rgba(20,20,20,0.14)" />
        </filter>
        <filter id="glowLong" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="rgba(224,69,69,0.45)" />
        </filter>
      </defs>

      <rect x={PAD_X} y={PAD_TOP} width={chartW} height={chartH / 2} fill="url(#zoneLong)" rx={8} opacity={gridOpacity} />
      <rect x={PAD_X} y={zeroY} width={chartW} height={chartH / 2} fill="url(#zoneShort)" rx={8} opacity={gridOpacity} />

      {[-0.5, 0.5].map((frac) => {
        const y = zeroY - frac * chartH;
        return (
          <line
            key={frac}
            x1={PAD_X}
            y1={y}
            x2={WIDTH - PAD_X}
            y2={y}
            stroke="#e8e4df"
            strokeWidth={1}
            strokeDasharray="5,5"
            opacity={gridOpacity}
          />
        );
      })}

      <line x1={PAD_X} y1={zeroY} x2={WIDTH - PAD_X} y2={zeroY} stroke="#cfc9c2" strokeWidth={2} opacity={gridOpacity} />

      {SYMBOLS.map((symbol, index) => {
        const value = data[symbol];
        const isPositive = value >= 0;
        const color = isPositive ? THEME.longDeep : THEME.shortDeep;
        const light = isPositive ? "#fff5f5" : "#f0faf5";
        const fill = isPositive ? "url(#gradLong)" : "url(#gradShort)";
        const cx = PAD_X + gap * index + gap / 2;
        const targetH = barHeight(value, maxAbs, chartH);
        const delay = startFrame + index * 8;
        const grow = holdOrSpring(isHold, animFrame, fps, delay, { damping: 18, stiffness: 120 });
        const labelOpacity = isHold
          ? 1
          : interpolate(animFrame, [delay + 6, delay + 18], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
        const animatedH = targetH * grow;
        const displayValue = Math.round(value * grow);
        const sign = displayValue >= 0 ? "+" : "";
        const x = cx - barW / 2;
        const barY = isPositive ? zeroY - animatedH : zeroY;
        const labelY = isPositive ? barY - 14 : barY + animatedH + 22;
        const rx = Math.min(barW / 2, 8);
        const compact = animatedH < 24;
        const badgeH = compact ? 20 : 22;
        const badgeW = compact ? 48 : 52;
        const badgeRx = compact ? 10 : 11;
        const fontSize = compact ? 10 : 12;
        const isPeak = index === maxIdx;
        const dotR = 3;
        const dotCy = isPositive ? labelY - 14 - 6 - dotR : labelY + 8 + 6 + dotR;

        return (
          <g key={symbol} opacity={labelOpacity}>
            <rect
              x={x}
              y={barY}
              width={barW}
              height={animatedH}
              fill={fill}
              rx={rx}
              filter={index === maxIdx && isPositive ? "url(#glowLong)" : "url(#barShadow)"}
            />
            <rect
              x={cx - badgeW / 2}
              y={labelY - 14}
              width={badgeW}
              height={badgeH}
              rx={badgeRx}
              fill={light}
              stroke={color}
              strokeWidth={1}
              opacity={0.95}
            />
            <text x={cx} y={labelY} textAnchor="middle" fontFamily={THEME.sans} fontSize={fontSize} fontWeight={800} fill={color}>
              {sign}
              {displayValue.toLocaleString("zh-CN")}
            </text>
            {isPeak ? <circle cx={cx} cy={dotCy} r={dotR} fill={color} /> : null}
            <text x={cx} y={axisY} textAnchor="middle" fontFamily={THEME.sans} fontSize={10} fontWeight={600} fill={THEME.inkSecondary}>
              {symbol} {SYMBOL_NAMES[symbol]}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
