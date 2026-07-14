import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { SeriesBadgeConfig } from "./types";

type SeriesBadgeProps = {
  badge: SeriesBadgeConfig;
};

export const SeriesBadge: React.FC<SeriesBadgeProps> = ({ badge }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationFrames = Math.round(badge.duration_sec * fps);

  if (frame > durationFrames) {
    return null;
  }

  const opacity = interpolate(frame, [0, 8, durationFrames - 8, durationFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 72,
        left: 48,
        pointerEvents: "none",
        opacity,
      }}
    >
      <div
        style={{
          padding: "10px 18px",
          borderRadius: 8,
          background: "rgba(12,10,8,0.55)",
          border: "1px solid rgba(240,216,168,0.28)",
          backdropFilter: "blur(6px)",
        }}
      >
        <div
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: "#f0d8a8",
            letterSpacing: "0.14em",
          }}
        >
          {badge.series}
          {badge.episode}
        </div>
      </div>
    </div>
  );
};
