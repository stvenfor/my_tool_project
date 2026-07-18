import type {ReactNode} from 'react';
import {AbsoluteFill} from 'remotion';
import {theme} from '../theme';

export const Background = ({children}: {children: ReactNode}) => {
  return (
    <AbsoluteFill
      style={{
        background: theme.background,
        color: theme.text,
        fontFamily: theme.font,
        overflow: 'hidden',
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.026) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.026) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage: 'linear-gradient(to bottom, black, transparent 82%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 760,
          height: 760,
          borderRadius: '50%',
          top: -420,
          right: -330,
          background: 'rgba(240, 75, 75, 0.12)',
          filter: 'blur(120px)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 700,
          height: 700,
          borderRadius: '50%',
          bottom: -410,
          left: -350,
          background: 'rgba(34, 184, 121, 0.10)',
          filter: 'blur(120px)',
        }}
      />
      {children}
    </AbsoluteFill>
  );
};
