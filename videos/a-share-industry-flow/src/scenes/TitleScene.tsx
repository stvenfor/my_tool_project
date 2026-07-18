import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

export const TitleScene = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entrance = interpolate(frame, [0, 0.58 * fps], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exit = interpolate(frame, [0.9 * fps, 1.2 * fps], [1, 0], {
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
        opacity: entrance * exit,
        transform: `translateY(${interpolate(entrance, [0, 1], [36, 0])}px)`,
      }}
    >
      <div style={{display: 'flex', gap: 12, marginBottom: 42}}>
        <div style={{width: 58, height: 8, borderRadius: 99, background: theme.inflow}} />
        <div style={{width: 28, height: 8, borderRadius: 99, background: theme.outflow}} />
      </div>
      <div style={{fontSize: 102, lineHeight: 1.1, fontWeight: 760, letterSpacing: -5}}>
        A 股行业
        <br />
        资金流向
      </div>
      <div style={{marginTop: 42, color: theme.muted, fontSize: 38, letterSpacing: 2}}>
        2026.07.17 · 收盘数据
      </div>
      <div
        style={{
          marginTop: 86,
          height: 1,
          background: 'linear-gradient(90deg, rgba(255,255,255,.28), transparent)',
        }}
      />
      <div style={{marginTop: 24, color: theme.subtle, fontSize: 24, letterSpacing: 3}}>
        A-SHARE CAPITAL FLOW
      </div>
    </div>
  );
};
