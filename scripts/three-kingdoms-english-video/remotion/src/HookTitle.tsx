import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { HookConfig } from "./types";

type HookTitleProps = {
  hook: HookConfig;
  seriesTitle?: string;
};

export const HookTitle: React.FC<HookTitleProps> = ({ hook, seriesTitle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationFrames = Math.round(hook.duration_sec * fps);

  if (frame > durationFrames) {
    return null;
  }

  const opacity = interpolate(frame, [0, 10, durationFrames - 10, durationFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [0, 14], [1.12, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lineWidth = interpolate(frame, [6, 20], [0, 120], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const glow = interpolate(frame, [0, durationFrames / 2, durationFrames], [0.6, 1, 0.7], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        pointerEvents: "none",
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
          padding: "28px 40px",
          borderRadius: 20,
          background: "radial-gradient(ellipse at center, rgba(20,14,8,0.55) 0%, rgba(0,0,0,0.15) 70%)",
          border: "1px solid rgba(255,230,180,0.18)",
        }}
      >
        <div
          style={{
            width: lineWidth,
            height: 2,
            background: "linear-gradient(90deg, transparent, #f0d8a8, transparent)",
            opacity: glow,
          }}
        />
        {seriesTitle ? (
          <div style={{ fontSize: 18, color: "#f0d8a8", letterSpacing: "0.2em", opacity: glow }}>
            {seriesTitle}
          </div>
        ) : null}
        <div
          style={{
            fontSize: 46,
            fontWeight: 700,
            color: "#fff8ec",
            letterSpacing: "0.16em",
            textAlign: "center",
            padding: "0 48px",
            textShadow: `0 0 ${18 * glow}px rgba(240,216,168,0.45), 0 4px 24px rgba(0,0,0,0.65)`,
            lineHeight: 1.5,
            WebkitTextStroke: "0.5px rgba(0,0,0,0.35)",
          }}
        >
          {hook.text_zh}
        </div>
        {hook.text_en ? (
          <div style={{ fontSize: 20, color: "#ffe066", letterSpacing: "0.06em" }}>{hook.text_en}</div>
        ) : null}
        <div
          style={{
            width: lineWidth,
            height: 2,
            background: "linear-gradient(90deg, transparent, #f0d8a8, transparent)",
            opacity: glow,
          }}
        />
      </div>
    </div>
  );
};
