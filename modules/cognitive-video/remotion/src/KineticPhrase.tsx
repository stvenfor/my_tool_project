import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { EmphasisItem, EmphasisStyle } from "./types";

type KineticPhraseProps = {
  items: EmphasisItem[];
  styleConfig: EmphasisStyle;
};

export const KineticPhrase: React.FC<KineticPhraseProps> = ({ items, styleConfig }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentSec = frame / fps;

  const active = items.find(
    (item) => currentSec >= item.start_sec && currentSec < item.start_sec + item.duration_sec,
  );

  if (!active) {
    return null;
  }

  const startFrame = Math.round(active.start_sec * fps);
  const endFrame = Math.round((active.start_sec + active.duration_sec) * fps);
  const opacity = interpolate(frame, [startFrame, startFrame + 6, endFrame - 6, endFrame], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [startFrame, startFrame + 10], [1.15, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const fontSize = styleConfig.font_size ?? 52;
  const color = styleConfig.color ?? "#ffe8b0";

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
          fontSize,
          fontWeight: 800,
          color,
          letterSpacing: "0.18em",
          textAlign: "center",
          padding: "0 56px",
          textShadow: "0 0 28px rgba(255,232,176,0.5), 0 4px 32px rgba(0,0,0,0.7)",
          WebkitTextStroke: "1px rgba(0,0,0,0.4)",
        }}
      >
        {active.text}
      </div>
    </div>
  );
};
