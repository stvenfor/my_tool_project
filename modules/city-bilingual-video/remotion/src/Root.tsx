import { Composition } from "remotion";
import { CityBilingualVideo, calculateCityBilingualMetadata } from "./CityBilingualVideo";
import type { CityBilingualVideoProps } from "./types";

const DEFAULT_STORYBOARD: CityBilingualVideoProps["storyboard"] = {
  style: "bilingual_travel",
  city_name: "西安",
  ancient_name: "长安",
  fps: 30,
  width: 1080,
  height: 1920,
  duration_sec: 51.233,
  duration_in_frames: 1537,
  transition_frames: 10,
  narration: "narration.wav",
  narration_volume: 1,
  bgm: "bgm.wav",
  bgm_volume: 0.35,
  hook: {
    text_zh: "白天是西安，晚上是长安",
    duration_sec: 2.5,
  },
  subtitles: [],
  subtitle_style: {
    zh_size: 34,
    en_size: 22,
    margin_bottom: 180,
    color_zh: "#ffffff",
    color_en: "#f0d8a8",
  },
  grade: {
    day_warmth: 0.15,
    night_warmth: 0.55,
    pivot_sec: 25,
  },
  shots: [],
  closing_title: {
    text_zh: "白天是西安，晚上是长安",
    text_en: "Day is Xi'an. Night is Chang'an.",
    appear_at_sec: 47,
    duration_sec: 4,
  },
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="CityBilingualVideo"
      component={CityBilingualVideo}
      durationInFrames={DEFAULT_STORYBOARD.duration_in_frames}
      fps={DEFAULT_STORYBOARD.fps}
      width={DEFAULT_STORYBOARD.width}
      height={DEFAULT_STORYBOARD.height}
      defaultProps={{
        storyboard: DEFAULT_STORYBOARD,
      } satisfies CityBilingualVideoProps}
      calculateMetadata={calculateCityBilingualMetadata}
    />
  );
};
