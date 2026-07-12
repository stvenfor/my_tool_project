import type { StoryboardData, ResolvedShot } from "./types";

export function resolveShots(storyboard: StoryboardData, fps: number): ResolvedShot[] {
  return storyboard.shots.map((shot) => ({
    ...shot,
    is_image: Boolean(shot.is_image),
    fromFrame: Math.round(shot.start_sec * fps),
    durationInFrames: Math.max(1, Math.round(shot.duration_sec * fps)),
    src: shot.clip,
  }));
}

export function getTotalFrames(storyboard: StoryboardData, fps: number): number {
  if (storyboard.shots?.length) {
    const ends = storyboard.shots.map((s) => s.start_sec + s.duration_sec);
    return Math.max(Math.round(storyboard.duration_sec * fps), Math.round(Math.max(...ends) * fps));
  }
  if (storyboard.duration_in_frames) {
    return storyboard.duration_in_frames;
  }
  return Math.round(storyboard.duration_sec * fps);
}
