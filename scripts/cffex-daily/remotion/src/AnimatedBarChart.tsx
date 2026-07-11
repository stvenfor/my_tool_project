import { interpolate, useVideoConfig } from "remotion";
import { SYMBOLS, SYMBOL_NAMES, THEME, type SymbolCode } from "./types";
import { holdOrInterpolate, holdOrSpring, useAnimFrame, useIsHold } from "./useAnimFrame";

type AnimatedBarChartProps = {
  data: Record<SymbolCode, number>;
  startFrame: number;
};

const WIDTH = 632;
const HEIGHT = 260;
const PAD_TOP = 32;
const PAD_BOTTOM = 52;
const PAD_X = 28;

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
  const barW = gap * 0.48;

  const gridOpacity = holdOrInterpolate(isHold, animFrame, [startFrame, startFrame + 12], [0, 1]);

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} style={{ width: "100%", height: "100%" }}>
      <defs>
        <linearGradient id="gradLong" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={THEME.long} />
          <stop offset="100%" stopColor={THEME.longDeep} />
        </linearGradient>
        <linearGradient id="gradShort" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor={THEME.short} />
          <stop offset="100%" stopColor={THEME.shortDeep} />
        </linearGradient>
      </defs>

      <rect x={PAD_X} y={PAD_TOP} width={chartW} height={chartH / 2} fill="rgba(209,77,77,0.10)" rx={4} opacity={gridOpacity} />
      <rect x={PAD_X} y={zeroY} width={chartW} height={chartH / 2} fill="rgba(58,154,106,0.10)" rx={4} opacity={gridOpacity} />

      {[-0.5, 0.5].map((frac) => {
        const y = zeroY - frac * chartH;
        return (
          <line
            key={frac}
            x1={PAD_X}
            y1={y}
            x2={WIDTH - PAD_X}
            y2={y}
            stroke={THEME.grid}
            strokeWidth={1}
            strokeDasharray="4,4"
            opacity={gridOpacity}
          />
        );
      })}

      <line x1={PAD_X} y1={zeroY} x2={WIDTH - PAD_X} y2={zeroY} stroke={THEME.line} strokeWidth={1.5} opacity={gridOpacity} />

      {SYMBOLS.map((symbol, index) => {
        const value = data[symbol];
        const isPositive = value >= 0;
        const color = isPositive ? THEME.longDeep : THEME.shortDeep;
        const fill = isPositive ? "url(#gradLong)" : "url(#gradShort)";
        const cx = PAD_X + gap * index + gap / 2;
        const barH = (Math.abs(value) / maxAbs) * (chartH / 2 - 16);
        const delay = startFrame + index * 8;
        const grow = holdOrSpring(isHold, animFrame, fps, delay, { damping: 18, stiffness: 120 });
        const labelOpacity = isHold
          ? 1
          : interpolate(animFrame, [delay + 6, delay + 18], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
        const animatedH = barH * grow;
        const displayValue = Math.round(value * grow);
        const sign = displayValue >= 0 ? "+" : "";
        const x = cx - barW / 2;
        const barY = isPositive ? zeroY - animatedH : zeroY;
        const labelY = isPositive ? barY - 10 : barY + animatedH + 18;
        const rx = animatedH > 6 ? 4 : 1;

        return (
          <g key={symbol}>
            {index === maxIdx && animatedH > 0 && (
              <rect
                x={x - 4}
                y={barY - 4}
                width={barW + 8}
                height={animatedH + 8}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                rx={6}
                opacity={0.35 * labelOpacity}
              />
            )}
            <rect x={x} y={barY} width={barW} height={animatedH} fill={fill} rx={rx} />
            <text
              x={cx}
              y={labelY}
              textAnchor="middle"
              fontFamily={THEME.sans}
              fontSize={13}
              fontWeight={800}
              fill={color}
              opacity={labelOpacity}
            >
              {sign}
              {displayValue.toLocaleString("zh-CN")}
            </text>
            <text
              x={cx}
              y={HEIGHT - 28}
              textAnchor="middle"
              fontFamily={THEME.sans}
              fontSize={12}
              fontWeight={700}
              fill={THEME.ink}
              opacity={labelOpacity}
            >
              {symbol}
            </text>
            <text
              x={cx}
              y={HEIGHT - 12}
              textAnchor="middle"
              fontFamily={THEME.sans}
              fontSize={10}
              fill={THEME.inkSecondary}
              opacity={labelOpacity}
            >
              {SYMBOL_NAMES[symbol]}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
