import { Composition } from "remotion";
import { CityHealingVideo, calculateCityHealingMetadata } from "./CityHealingVideo";
import type { CityHealingVideoProps } from "./types";

const DEFAULT_STORYBOARD: CityHealingVideoProps["storyboard"] = {
  city_name: "【目标城市】",
  fps: 30,
  width: 1080,
  height: 1920,
  duration_sec: 60,
  duration_in_frames: 1800,
  transition_frames: 12,
  narration: "narration.wav",
  bgm: "",
  bgm_volume: 0.12,
  shots: [],
  data_cards: [
    {
      id: "population",
      label: "常住人口",
      value: 38,
      unit: "万人",
      appear_at_sec: 32,
      duration_sec: 2.5,
    },
  ],
  closing_title: {
    text: "【目标城市】",
    appear_at_sec: 54,
    duration_sec: 6,
  },
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="CityHealingVideo"
      component={CityHealingVideo}
      durationInFrames={DEFAULT_STORYBOARD.duration_in_frames}
      fps={DEFAULT_STORYBOARD.fps}
      width={DEFAULT_STORYBOARD.width}
      height={DEFAULT_STORYBOARD.height}
      defaultProps={{
        storyboard: DEFAULT_STORYBOARD,
      } satisfies CityHealingVideoProps}
      calculateMetadata={calculateCityHealingMetadata}
    />
  );
};
