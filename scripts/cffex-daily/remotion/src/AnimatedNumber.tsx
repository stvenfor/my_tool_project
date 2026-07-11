import { interpolate } from "remotion";
import { useAnimFrame, useIsHold } from "./useAnimFrame";

type AnimatedNumberProps = {
  value: number;
  startFrame: number;
  durationFrames: number;
  formatter?: (value: number) => string;
  style?: React.CSSProperties;
};

export const AnimatedNumber: React.FC<AnimatedNumberProps> = ({
  value,
  startFrame,
  durationFrames,
  formatter = (v) => Math.round(v).toLocaleString("zh-CN"),
  style,
}) => {
  const isHold = useIsHold();
  const animFrame = useAnimFrame();

  const progress = isHold
    ? 1
    : interpolate(animFrame, [startFrame, startFrame + durationFrames], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
  const eased = 1 - Math.pow(1 - progress, 3);
  const current = value * eased;

  return <span style={style}>{formatter(current)}</span>;
};
