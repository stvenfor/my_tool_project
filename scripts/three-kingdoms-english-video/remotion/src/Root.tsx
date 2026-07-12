import { Composition } from "remotion";
import { ThreeKingdomsEnglishVideo, calculateThreeKingdomsMetadata } from "./ThreeKingdomsEnglishVideo";
import type { ThreeKingdomsEnglishVideoProps } from "./types";

const DEFAULT_STORYBOARD: ThreeKingdomsEnglishVideoProps["storyboard"] = {
  style: "three_kingdoms_english",
  series_title: "儿童英语三国",
  episode_title: "移驾许昌",
  episode_hook: "从此曹操霸业开始",
  fps: 30,
  width: 1080,
  height: 1920,
  duration_sec: 141.767,
  duration_in_frames: 4253,
  transition_frames: 8,
  narration: "narration.wav",
  narration_volume: 0.85,
  bgm: "bgm.wav",
  bgm_volume: 0.25,
  hook: {
    text_zh: "儿童英语三国【移驾许昌】",
    text_en: "Three Kingdoms English: Move to Xuchang",
    duration_sec: 3,
  },
  subtitles: [],
  subtitle_style: {
    zh_size: 28,
    en_size: 22,
    margin_top: 80,
    color_zh: "#ffffff",
    color_en: "#ffe066",
  },
  shots: [],
  closing_title: {
    text_zh: "【移驾许昌】从此曹操霸业开始",
    text_en: "Cao Cao's power grew from here.",
    appear_at_sec: 136,
    duration_sec: 5,
  },
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="ThreeKingdomsEnglishVideo"
      component={ThreeKingdomsEnglishVideo}
      durationInFrames={DEFAULT_STORYBOARD.duration_in_frames}
      fps={DEFAULT_STORYBOARD.fps}
      width={DEFAULT_STORYBOARD.width}
      height={DEFAULT_STORYBOARD.height}
      defaultProps={{ storyboard: DEFAULT_STORYBOARD } satisfies ThreeKingdomsEnglishVideoProps}
      calculateMetadata={calculateThreeKingdomsMetadata}
    />
  );
};
