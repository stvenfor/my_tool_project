import { Composition } from "remotion";
import { ViralDubVideo, calculateViralDubMetadata } from "./ViralDubVideo";
import type { ViralDubVideoProps } from "./types";

const DEFAULT_STORYBOARD: ViralDubVideoProps["storyboard"] = {
  style: "viral_english_dub",
  clip_id: "demo-clip",
  title: "Classic scene in English",
  fps: 30,
  width: 1080,
  height: 1920,
  duration_sec: 33,
  duration_in_frames: 990,
  source_video: "reference/source.mp4",
  narration: "narration.wav",
  narration_volume: 0.92,
  bgm: "",
  bgm_volume: 0.08,
  show_hook_title: true,
  hook: {
    text_en: "Classic scene in English",
    duration_sec: 1.5,
  },
  subtitles: [],
  subtitle_style: {
    en_size: 28,
    zh_size: 22,
    margin_bottom: 160,
    color_en: "#ffffff",
    color_zh: "#f0d8a8",
  },
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="ViralDubVideo"
      component={ViralDubVideo}
      durationInFrames={DEFAULT_STORYBOARD.duration_in_frames}
      fps={DEFAULT_STORYBOARD.fps}
      width={DEFAULT_STORYBOARD.width}
      height={DEFAULT_STORYBOARD.height}
      defaultProps={{
        storyboard: DEFAULT_STORYBOARD,
      } satisfies ViralDubVideoProps}
      calculateMetadata={calculateViralDubMetadata}
    />
  );
};
