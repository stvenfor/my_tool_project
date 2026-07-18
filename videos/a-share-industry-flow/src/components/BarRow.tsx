import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {z} from 'zod';
import type {flowItemSchema} from '../schema';
import {theme} from '../theme';

type FlowItem = z.infer<typeof flowItemSchema>;

export const BarRow = ({
  item,
  index,
  maximum,
  direction,
}: {
  item: FlowItem;
  index: number;
  maximum: number;
  direction: 'inflow' | 'outflow';
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const delay = index * 3;
  const progress = spring({
    frame: frame - delay,
    fps,
    durationInFrames: 18,
    config: {damping: 200},
  });
  const reveal = interpolate(progress, [0, 1], [18, 0]);
  const value = item.netAmount * progress;
  const width = Math.max(4, (Math.abs(item.netAmount) / maximum) * 100 * progress);
  const color = direction === 'inflow' ? theme.inflow : theme.outflow;
  const bright = direction === 'inflow' ? theme.inflowBright : theme.outflowBright;
  const formatted = `${value >= 0 ? '+' : '-'}${Math.abs(value).toFixed(2)} 亿元`;

  return (
    <div
      style={{
        opacity: progress,
        transform: `translateY(${reveal}px)`,
        height: 162,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        gap: 18,
      }}
    >
      <div style={{display: 'flex', alignItems: 'baseline', gap: 18}}>
        <div
          style={{
            color: item.rank === 1 ? bright : theme.subtle,
            fontSize: 30,
            fontWeight: 700,
            width: 42,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {String(item.rank).padStart(2, '0')}
        </div>
        <div
          style={{
            color: theme.text,
            fontSize: item.industry.length > 8 ? 34 : 39,
            fontWeight: 650,
            letterSpacing: -0.5,
            flex: 1,
            whiteSpace: 'nowrap',
          }}
        >
          {item.industry}
        </div>
        <div
          style={{
            color: bright,
            fontSize: 32,
            fontWeight: 700,
            fontVariantNumeric: 'tabular-nums',
            minWidth: 250,
            textAlign: 'right',
          }}
        >
          {formatted}
        </div>
      </div>
      <div
        style={{
          height: 20,
          marginLeft: 60,
          borderRadius: 999,
          overflow: 'hidden',
          background: 'rgba(255,255,255,0.055)',
          boxShadow: item.rank === 1 ? `0 0 0 1px ${color}33` : undefined,
        }}
      >
        <div
          style={{
            width: `${width}%`,
            height: '100%',
            borderRadius: 999,
            background: `linear-gradient(90deg, ${color}99, ${bright})`,
            boxShadow: item.rank === 1 ? `0 0 28px ${color}66` : undefined,
          }}
        />
      </div>
    </div>
  );
};
