import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { PhaseTheme } from "./theme";
import { useVideoLayout } from "../useVideoLayout";

type Props = {
  theme: PhaseTheme;
};

export const StickmanSceneBackground: React.FC<Props> = ({ theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { isLandscape } = useVideoLayout();

  const driftA = interpolate(Math.sin(frame / (fps * 2.2)), [-1, 1], [-18, 18]);
  const driftB = interpolate(Math.cos(frame / (fps * 1.8)), [-1, 1], [-14, 14]);
  const pulse = interpolate(Math.sin(frame / (fps * 1.1)), [-1, 1], [0.92, 1.06]);

  return (
    <>
      <div style={{ position: "absolute", inset: 0, background: theme.background }} />
      <div
        style={{
          position: "absolute",
          top: (isLandscape ? 80 : 180) + driftA,
          left: -40 + driftB,
          width: (isLandscape ? 220 : 280) * pulse,
          height: (isLandscape ? 220 : 280) * pulse,
          borderRadius: "50%",
          background: theme.orb,
          filter: "blur(40px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: (isLandscape ? 120 : 220) - driftB,
          right: -20 + driftA * 0.5,
          width: isLandscape ? 180 : 220,
          height: isLandscape ? 180 : 220,
          borderRadius: "50%",
          background: theme.accentSoft,
          filter: "blur(36px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(0,0,0,0.035) 1px, transparent 0)",
          backgroundSize: "28px 28px",
          opacity: 0.35,
        }}
      />
    </>
  );
};
