import type { MontageCut, MontageData, ResolvedCut } from "./types";

export function resolveCuts(montage: MontageData, fps: number): ResolvedCut[] {
  const beats = montage.beats;
  const resolved: ResolvedCut[] = [];

  for (const cut of montage.cuts) {
    const startBeat = Math.min(cut.startBeat, Math.max(beats.length - 1, 0));
    const startTime = cut.startTime ?? beats[startBeat] ?? 0;
    const beatDuration =
      cut.duration ??
      Math.max(
        1 / fps,
        (beats[Math.min(startBeat + cut.durationBeats, beats.length - 1)] ?? montage.duration) - startTime,
      );
    const durationSeconds = Math.max(1 / fps, beatDuration);
    const lower = cut.clip.toLowerCase();
    const isImage = /\.(png|jpe?g|webp|gif)$/.test(lower);
    const src = cut.clip.startsWith("clips/") ? cut.clip : `clips/${cut.clip}`;

    resolved.push({
      ...cut,
      fromFrame: Math.round(startTime * fps),
      durationInFrames: Math.max(1, Math.round(durationSeconds * fps)),
      src,
      isImage,
    });
  }

  return resolved;
}

export function getTotalFrames(montage: MontageData, fps: number): number {
  return Math.max(1, Math.ceil(montage.duration * fps));
}
