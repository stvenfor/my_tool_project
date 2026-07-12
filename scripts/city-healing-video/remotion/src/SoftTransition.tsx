import { interpolate, useCurrentFrame } from "remotion";

type SoftTransitionProps = {
  children: React.ReactNode;
  durationInFrames: number;
  transitionFrames: number;
};

export const SoftTransition: React.FC<SoftTransitionProps> = ({
  children,
  durationInFrames,
  transitionFrames,
}) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, transitionFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - transitionFrames, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <div style={{ width: "100%", height: "100%", opacity }}>
      {children}
    </div>
  );
};

type KenBurnsProps = {
  children: React.ReactNode;
  enabled: boolean;
  durationInFrames: number;
};

export const KenBurns: React.FC<KenBurnsProps> = ({ children, enabled, durationInFrames }) => {
  const frame = useCurrentFrame();
  const scale = enabled
    ? interpolate(frame, [0, durationInFrames], [1.04, 1.0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transform: `scale(${scale})`,
        transformOrigin: "center center",
      }}
    >
      {children}
    </div>
  );
};
