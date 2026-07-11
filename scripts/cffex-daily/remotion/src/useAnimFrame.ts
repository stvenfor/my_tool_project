import { interpolate, spring, useCurrentFrame } from "remotion";
import { HOLD_FRAMES } from "./constants";

export function useAnimFrame(): number {
  return Math.max(0, useCurrentFrame() - HOLD_FRAMES);
}

export function useIsHold(): boolean {
  return useCurrentFrame() < HOLD_FRAMES;
}

export function holdOrSpring(
  isHold: boolean,
  animFrame: number,
  fps: number,
  startFrame: number,
  config: { damping: number; stiffness: number },
): number {
  if (isHold) return 1;
  return spring({
    frame: animFrame - startFrame,
    fps,
    config,
  });
}

export function holdOrInterpolate(
  isHold: boolean,
  animFrame: number,
  inputRange: [number, number],
  outputRange: [number, number],
): number {
  if (isHold) return outputRange[1];
  return interpolate(animFrame, inputRange, outputRange, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}
