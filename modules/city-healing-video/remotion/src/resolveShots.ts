import type { StoryboardData } from "./types";
import type { ResolvedShot } from "./types";

export function resolveShots(storyboard: StoryboardData, fps: number): ResolvedShot[] {
  return storyboard.shots.map((shot) => ({
    ...shot,
    fromFrame: Math.round(shot.start_sec * fps),
    durationInFrames: Math.max(1, Math.round(shot.duration_sec * fps)),
    src: shot.clip,
  }));
}

export function getTotalFrames(storyboard: StoryboardData, fps: number): number {
  if (storyboard.duration_in_frames) {
    return storyboard.duration_in_frames;
  }
  return Math.round(storyboard.duration_sec * fps);
}
