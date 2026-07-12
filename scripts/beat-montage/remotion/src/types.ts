export type MontageSection = {
  name: string;
  start: number;
  end: number;
};

export type MontageCut = {
  clip: string;
  clipId?: string;
  section?: string;
  startBeat: number;
  startTime?: number;
  durationBeats: number;
  duration?: number;
  trimIn: number;
  fx: Array<"flash" | "zoom">;
  description?: string;
  actionSync?: string;
  referenceCut?: number;
  beatSnapMs?: number;
};

export type MontageData = {
  title?: string;
  audio: string;
  fps: number;
  width: number;
  height: number;
  playbackRate?: number;
  duration: number;
  bpm?: number;
  sections?: MontageSection[];
  beats: number[];
  cuts: MontageCut[];
  syncMode?: string;
};

export type BeatMontageVideoProps = {
  montage: MontageData;
};

export type ResolvedCut = MontageCut & {
  fromFrame: number;
  durationInFrames: number;
  src: string;
  isImage: boolean;
};
