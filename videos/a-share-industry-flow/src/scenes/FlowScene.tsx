import {Easing, interpolate, useCurrentFrame} from 'remotion';
import type {z} from 'zod';
import {BarRow} from '../components/BarRow';
import type {flowItemSchema} from '../schema';
import {theme} from '../theme';

type FlowItem = z.infer<typeof flowItemSchema>;

export const FlowScene = ({
  items,
  direction,
  sceneDuration,
}: {
  items: FlowItem[];
  direction: 'inflow' | 'outflow';
  sceneDuration: number;
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(
    frame,
    [0, 4, sceneDuration - 4, sceneDuration],
    [0, 1, 1, 0],
    {
      easing: Easing.inOut(Easing.quad),
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );
  const displayItems = [...items].reverse();
  const maximum = Math.max(...items.map((item) => Math.abs(item.netAmount)));
  const isInflow = direction === 'inflow';
  const accent = isInflow ? theme.inflow : theme.outflow;
  const title = isInflow ? '行业净流入 TOP 5' : '行业净流出 TOP 5';

  return (
    <div
      style={{
        position: 'absolute',
        inset: 72,
        opacity,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{paddingTop: 70, display: 'flex', justifyContent: 'space-between'}}>
        <div>
          <div style={{fontSize: 28, color: accent, fontWeight: 700, letterSpacing: 2}}>
            2026.07.17 · CLOSE
          </div>
          <div style={{fontSize: 61, fontWeight: 750, marginTop: 14, letterSpacing: -2}}>{title}</div>
        </div>
        <div
          style={{
            alignSelf: 'flex-start',
            padding: '14px 20px',
            borderRadius: 999,
            color: theme.muted,
            border: `1px solid ${theme.panelEdge}`,
            fontSize: 23,
          }}
        >
          单位：亿元
        </div>
      </div>

      <div
        style={{
          marginTop: 82,
          padding: '34px 38px',
          borderRadius: 34,
          background: theme.panel,
          border: `1px solid ${theme.panelEdge}`,
          boxShadow: '0 28px 90px rgba(0,0,0,.28)',
        }}
      >
        {displayItems.map((item, index) => (
          <BarRow
            key={item.industry}
            item={item}
            index={index}
            maximum={maximum}
            direction={direction}
          />
        ))}
      </div>

      <div
        style={{
          marginTop: 'auto',
          paddingBottom: 44,
          color: theme.subtle,
          fontSize: 23,
          lineHeight: 1.7,
        }}
      >
        <div>来源：同花顺行业资金流 / AKShare</div>
        <div>数据截至：2026-07-17 15:00 CST</div>
      </div>
    </div>
  );
};
