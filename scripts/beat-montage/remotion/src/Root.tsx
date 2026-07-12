import { Composition } from "remotion";
import {
  BeatMontageVideo,
  calculateMontageMetadata,
  type BeatMontageVideoProps,
} from "./BeatMontageVideo";
import type { MontageData } from "./types";

const DEFAULT_MONTAGE: MontageData = {
  title: "打击乐版红日踩点混剪",
  audio: "bgm/sample.mp3",
  fps: 30,
  width: 1080,
  height: 1920,
  playbackRate: 1.01,
  duration: 15,
  bpm: 128,
  beats: [0, 0.47, 0.94, 1.41, 1.88, 2.34, 2.81, 3.28],
  cuts: [
    {
      clip: "clips/comedy/bean_01.png",
      startBeat: 0,
      durationBeats: 2,
      trimIn: 0,
      fx: [],
    },
  ],
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="BeatMontageVideo"
      component={BeatMontageVideo}
      durationInFrames={450}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        montage: DEFAULT_MONTAGE,
      } satisfies BeatMontageVideoProps}
      calculateMetadata={calculateMontageMetadata}
    />
  );
};
