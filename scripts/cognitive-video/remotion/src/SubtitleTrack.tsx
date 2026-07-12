import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { SubtitleSegment, SubtitleStyle } from "./types";
import { useVideoLayout } from "./useVideoLayout";

type SubtitleTrackProps = {
  segments: SubtitleSegment[];
  styleConfig: SubtitleStyle;
  visualStyle?: "cinematic" | "stickman";
};

export const SubtitleTrack: React.FC<SubtitleTrackProps> = ({
  segments,
  styleConfig,
  visualStyle = "cinematic",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const layout = useVideoLayout();
  const currentSec = frame / fps;

  const active = segments.find(
    (seg) => currentSec >= seg.start_sec && currentSec < seg.start_sec + seg.duration_sec,
  );

  if (!active?.zh) {
    return null;
  }

  const startFrame = Math.round(active.start_sec * fps);
  const endFrame = Math.round((active.start_sec + active.duration_sec) * fps);
  const instant = visualStyle === "stickman";
  const opacity = instant
    ? 1
    : interpolate(frame, [startFrame, startFrame + 8, endFrame - 8, endFrame], [0, 1, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
  const translateY = instant
    ? 0
    : interpolate(frame, [startFrame, startFrame + 10], [16, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });

  const zhSize = styleConfig.zh_size ?? (visualStyle === "stickman" ? layout.subtitleSize : 36);
  const marginBottom = styleConfig.margin_bottom ?? (visualStyle === "stickman" ? (layout.isLandscape ? 64 : 72) : 200);
  const shadow = styleConfig.shadow ?? (visualStyle === "stickman" ? "none" : "0 2px 12px rgba(0,0,0,0.55)");
  const speakerColors: Record<string, string> = {
    阿狸: "#ffd98a",
    大橘: "#ffb07a",
    小白: "#f5f5ff",
  };
  const speakerColor = active.speaker ? speakerColors[active.speaker] ?? "#ffe8b0" : "#ffe8b0";

  if (visualStyle === "stickman") {
    return (
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            borderTop: "1.5px solid rgba(17,17,17,0.1)",
            background: "rgba(255,255,255,0.94)",
            backdropFilter: "blur(10px)",
            padding: layout.isLandscape ? "18px 48px 22px" : "26px 36px 38px",
            boxShadow: "0 -8px 24px rgba(0,0,0,0.04)",
            opacity,
            transform: `translateY(${translateY}px)`,
          }}
        >
          <div
            style={{
              fontSize: zhSize,
              fontWeight: 700,
              color: "#111",
              textAlign: "center",
              lineHeight: 1.45,
              letterSpacing: "0.04em",
            }}
          >
            {active.zh}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: marginBottom,
        display: "flex",
        justifyContent: "center",
        padding: "0 32px",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          padding: "16px 24px",
          borderRadius: 16,
          background: "linear-gradient(180deg, rgba(8,8,12,0.45) 0%, rgba(8,8,12,0.65) 100%)",
          border: "1px solid rgba(255,236,200,0.14)",
          backdropFilter: "blur(8px)",
          opacity,
          transform: `translateY(${translateY}px)`,
          maxWidth: "92%",
        }}
      >
        {active.speaker ? (
          <div
            style={{
              fontSize: Math.round(zhSize * 0.72),
              fontWeight: 700,
              color: speakerColor,
              textAlign: "center",
              marginBottom: 8,
              letterSpacing: "0.14em",
              textShadow: shadow,
            }}
          >
            {active.speaker}
          </div>
        ) : null}
        <div
          style={{
            fontSize: zhSize,
            fontWeight: 700,
            color: styleConfig.color_zh ?? "#ffffff",
            textShadow: shadow,
            textAlign: "center",
            lineHeight: 1.4,
            letterSpacing: "0.06em",
            WebkitTextStroke: "0.5px rgba(0,0,0,0.45)",
          }}
        >
          {active.zh}
        </div>
      </div>
    </div>
  );
};
