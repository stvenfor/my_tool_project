import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { themeForPhase } from "./theme";
import { useVideoLayout } from "../useVideoLayout";

type StickmanEndCardProps = {
  textZh: string;
  appearAtSec: number;
  durationSec: number;
};

export const StickmanEndCard: React.FC<StickmanEndCardProps> = ({
  textZh,
  appearAtSec,
  durationSec,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const layout = useVideoLayout();
  const theme = themeForPhase("cta");
  const startFrame = Math.round(appearAtSec * fps);
  const endFrame = Math.round((appearAtSec + durationSec) * fps);

  if (frame < startFrame) {
    return null;
  }

  const local = frame - startFrame;
  const enter = spring({
    frame: local,
    fps,
    config: { damping: 14, stiffness: 160 },
  });
  const fadeOut = interpolate(frame, [endFrame - fps * 0.4, endFrame], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        pointerEvents: "none",
        zIndex: 8,
        opacity: enter * fadeOut,
      }}
    >
      <div
        style={{
          borderTop: `2px solid ${theme.accent}`,
          background: `linear-gradient(180deg, ${theme.cardBg} 0%, rgba(255,255,255,0.98) 100%)`,
          backdropFilter: "blur(12px)",
          padding: layout.isLandscape ? "22px 40px 28px" : "32px 36px 42px",
          boxShadow: "0 -12px 32px rgba(0,0,0,0.08)",
          transform: `translateY(${(1 - enter) * 24}px)`,
        }}
      >
        <div
          style={{
            fontSize: layout.endCardLabelSize,
            fontWeight: 700,
            color: theme.accent,
            textAlign: "center",
            letterSpacing: "0.18em",
            marginBottom: 12,
          }}
        >
          建议收藏
        </div>
        <div
          style={{
            fontSize: layout.endCardTitleSize,
            fontWeight: 800,
            color: "#111",
            textAlign: "center",
            lineHeight: 1.45,
            letterSpacing: "0.05em",
          }}
        >
          {textZh}
        </div>
      </div>
    </div>
  );
};
