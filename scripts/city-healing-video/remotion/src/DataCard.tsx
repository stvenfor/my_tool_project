import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { DataCard as DataCardType } from "./types";

type DataCardProps = {
  card: DataCardType;
};

export const DataCard: React.FC<DataCardProps> = ({ card }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const startFrame = Math.round(card.appear_at_sec * fps);
  const totalFrames = Math.round(card.duration_sec * fps);
  const fadeFrames = Math.round(0.5 * fps);

  const opacity = interpolate(
    frame,
    [startFrame, startFrame + fadeFrames, startFrame + totalFrames - fadeFrames, startFrame + totalFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const translateY = interpolate(
    frame,
    [startFrame, startFrame + fadeFrames],
    [8, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  if (frame < startFrame || frame > startFrame + totalFrames) {
    return null;
  }

  return (
    <div
      style={{
        position: "absolute",
        right: 48,
        bottom: 48,
        width: 240,
        padding: "14px 16px",
        borderRadius: 12,
        background: "rgba(255, 248, 235, 0.42)",
        border: "1px solid rgba(232, 208, 181, 0.8)",
        backdropFilter: "blur(6px)",
        opacity,
        transform: `translateY(${translateY}px)`,
        boxShadow: "0 8px 24px rgba(80, 60, 40, 0.12)",
      }}
    >
      <div
        style={{
          fontSize: 11,
          color: "#8b7355",
          letterSpacing: "0.04em",
          marginBottom: 6,
        }}
      >
        {card.label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span
          style={{
            fontSize: 22,
            fontWeight: 700,
            color: "#fff8ef",
            textShadow: "0 1px 4px rgba(60, 40, 20, 0.35)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {card.value.toLocaleString("zh-CN")}
        </span>
        <span style={{ fontSize: 12, color: "#d9c5a8" }}>{card.unit}</span>
      </div>
    </div>
  );
};
