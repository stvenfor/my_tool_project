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
  exitStartFrame: number;
}> = ({ text, fontSize, fontWeight, color, shadow, stroke, delayFrames, exitStartFrame }) => {
  const frame = useCurrentFrame();
  const enterEnd = Math.min(delayFrames + 10, exitStartFrame - 1);
  const fadeOutStart = Math.max(enterEnd + 1, exitStartFrame - 6);
  const opacity =
    enterEnd <= delayFrames || fadeOutStart >= exitStartFrame
      ? frame >= delayFrames && frame <= exitStartFrame
        ? 1
        : 0
      : interpolate(
          frame,
          [delayFrames, enterEnd, fadeOutStart, exitStartFrame],
          [0, 1, 1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        );
  const translateY =
    enterEnd <= delayFrames
      ? 0
      : interpolate(frame, [delayFrames, enterEnd], [18, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const scale =
    enterEnd <= delayFrames
      ? 1
      : interpolate(frame, [delayFrames, enterEnd], [0.94, 1], {
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
        letterSpacing: fontSize > 28 ? "0.04em" : "0.03em",
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
  const endFrame = Math.max(startFrame + 2, Math.round((active.start_sec + active.duration_sec) * fps));
  const boxFadeInEnd = Math.min(startFrame + 8, endFrame - 1);
  const boxFadeOutStart = Math.max(boxFadeInEnd + 1, endFrame - 8);
  const boxOpacity =
    boxFadeOutStart >= endFrame || boxFadeInEnd <= startFrame
      ? 1
      : interpolate(frame, [startFrame, boxFadeInEnd, boxFadeOutStart, endFrame], [0, 1, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const boxScaleEnd = Math.min(startFrame + 10, endFrame - 1);
  const boxScale =
    boxScaleEnd <= startFrame
      ? 1
      : interpolate(frame, [startFrame, boxScaleEnd], [0.96, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

  const enSize = styleConfig.en_size ?? 28;
  const zhSize = styleConfig.zh_size ?? 22;
  const marginBottom = styleConfig.margin_bottom ?? 160;
  const shadow = styleConfig.shadow ?? "0 2px 12px rgba(0,0,0,0.75)";
  const position = styleConfig.position ?? "bottom";
  const isCenter = position === "center";

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        ...(isCenter
          ? { top: "50%", transform: "translateY(-50%)" }
          : { bottom: marginBottom }),
        display: "flex",
        justifyContent: "center",
        padding: "0 32px",
        pointerEvents: "none",
        zIndex: 20,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 6,
          padding: isCenter ? "10px 18px" : "4px 8px",
          borderRadius: isCenter ? 14 : 0,
          background: isCenter
            ? "linear-gradient(180deg, rgba(8,8,12,0.45) 0%, rgba(8,8,12,0.62) 100%)"
            : "transparent",
          border: isCenter ? "1px solid rgba(255,236,200,0.12)" : "none",
          boxShadow: isCenter ? "0 8px 24px rgba(0,0,0,0.28)" : "none",
          backdropFilter: isCenter ? "blur(8px)" : undefined,
          opacity: boxOpacity,
          transform: isCenter ? undefined : `scale(${boxScale})`,
          maxWidth: "92%",
        }}
      >
        {active.en ? (
          <AnimatedLine
            text={active.en}
            fontSize={enSize}
            fontWeight={700}
            color={styleConfig.color_en ?? "#ffffff"}
            shadow={shadow}
            stroke="1.2px rgba(0,0,0,0.72)"
            delayFrames={startFrame}
            exitStartFrame={endFrame}
          />
        ) : null}
        {active.zh ? (
          <AnimatedLine
            text={active.zh}
            fontSize={zhSize}
            fontWeight={500}
            color={styleConfig.color_zh ?? "#f0d8a8"}
            shadow={shadow}
            stroke="0.9px rgba(0,0,0,0.65)"
            delayFrames={startFrame + 4}
            exitStartFrame={endFrame}
          />
        ) : null}
      </div>
    </div>
  );
};
