import { interpolate, useCurrentFrame } from "remotion";
import type { ReactNode } from "react";

type CinematicTransitionProps = {
  children: ReactNode;
  durationInFrames: number;
  transitionFrames: number;
};

export const CinematicTransition: React.FC<CinematicTransitionProps> = ({
  children,
  durationInFrames,
  transitionFrames,
}) => {
  const frame = useCurrentFrame();
  const fadeFrames = Math.max(4, Math.min(transitionFrames, 12));

  const fadeIn = interpolate(frame, [0, fadeFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fadeFrames, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = Math.min(fadeIn, fadeOut);

  const scale = interpolate(frame, [0, durationInFrames], [1.03, 1.0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        opacity,
        transform: `scale(${scale})`,
        transformOrigin: "center center",
        willChange: "opacity, transform",
      }}
    >
      {children}
    </div>
  );
};
