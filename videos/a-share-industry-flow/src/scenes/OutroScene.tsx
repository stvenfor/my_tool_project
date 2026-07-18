import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

export const OutroScene = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = interpolate(frame, [0, 0.65 * fps], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        inset: 72,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [28, 0])}px)`,
      }}
    >
      <div style={{width: 72, height: 8, borderRadius: 99, background: theme.inflow}} />
      <div style={{fontSize: 65, lineHeight: 1.28, fontWeight: 720, marginTop: 44}}>
        数据仅供市场观察
        <br />
        不构成投资建议
      </div>
      <div style={{fontSize: 28, lineHeight: 1.8, color: theme.muted, marginTop: 70}}>
        来源：同花顺行业资金流 / AKShare
        <br />
        数据截至：2026-07-17 15:00 CST
      </div>
    </div>
  );
};
