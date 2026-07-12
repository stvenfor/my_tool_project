import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { SubtitleSegment, SubtitleStyle } from "./types";

type BilingualSubtitleProps = {
  segments: SubtitleSegment[];
  styleConfig: SubtitleStyle;
};

const AnimatedLine: React.FC<{
  text: string;
  fontSize: number;
  fontWeight: number;
  color: string;
  shadow: string;
  stroke?: string;
  delayFrames: number;
  durationFrames: number;
  exitStartFrame: number;
}> = ({
  text,
  fontSize,
  fontWeight,
  color,
  shadow,
  stroke,
  delayFrames,
  durationFrames,
  exitStartFrame,
}) => {
  const frame = useCurrentFrame();
  const enterEnd = delayFrames + 10;
  const opacity = interpolate(
    frame,
    [delayFrames, enterEnd, exitStartFrame - 6, exitStartFrame],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const translateY = interpolate(frame, [delayFrames, enterEnd], [18, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [delayFrames, enterEnd], [0.94, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (frame < delayFrames || frame > exitStartFrame) {
    return null;
  }

  return (
    <div
      style={{
        fontSize,
        fontWeight,
        color,
        textShadow: shadow,
        WebkitTextStroke: stroke,
        textAlign: "center",
        lineHeight: 1.35,
        opacity,
        transform: `translateY(${translateY}px) scale(${scale})`,
        letterSpacing: fontSize > 28 ? "0.06em" : "0.03em",
      }}
    >
      {text}
    </div>
  );
};

export const BilingualSubtitle: React.FC<BilingualSubtitleProps> = ({ segments, styleConfig }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentSec = frame / fps;

  const active = segments.find(
    (seg) => currentSec >= seg.start_sec && currentSec < seg.start_sec + seg.duration_sec,
  );

  if (!active) {
    return null;
  }

  const startFrame = Math.round(active.start_sec * fps);
  const endFrame = Math.round((active.start_sec + active.duration_sec) * fps);
  const boxOpacity = interpolate(frame, [startFrame, startFrame + 8, endFrame - 8, endFrame], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const boxScale = interpolate(frame, [startFrame, startFrame + 10], [0.96, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const zhSize = styleConfig.zh_size ?? 34;
  const enSize = styleConfig.en_size ?? 22;
  const marginBottom = styleConfig.margin_bottom ?? 180;
  const shadow = styleConfig.shadow ?? "0 2px 12px rgba(0,0,0,0.55), 0 0 24px rgba(0,0,0,0.35)";

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
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 10,
          padding: "18px 28px",
          borderRadius: 18,
          background: "linear-gradient(180deg, rgba(8,8,12,0.42) 0%, rgba(8,8,12,0.62) 100%)",
          border: "1px solid rgba(255,236,200,0.14)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
          opacity: boxOpacity,
          transform: `scale(${boxScale})`,
          maxWidth: "92%",
        }}
      >
        {active.zh ? (
          <AnimatedLine
            text={active.zh}
            fontSize={zhSize}
            fontWeight={700}
            color={styleConfig.color_zh ?? "#ffffff"}
            shadow={shadow}
            stroke="0.5px rgba(0,0,0,0.45)"
            delayFrames={startFrame}
            durationFrames={endFrame - startFrame}
            exitStartFrame={endFrame}
          />
        ) : null}
        {active.en ? (
          <AnimatedLine
            text={active.en}
            fontSize={enSize}
            fontWeight={500}
            color={styleConfig.color_en ?? "#f0d8a8"}
            shadow={shadow}
            delayFrames={startFrame + 4}
            durationFrames={endFrame - startFrame}
            exitStartFrame={endFrame}
          />
        ) : null}
      </div>
    </div>
  );
};
