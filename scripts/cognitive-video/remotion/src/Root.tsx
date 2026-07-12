import { Composition } from "remotion";
import { CognitiveVideo, calculateCognitiveMetadata } from "./CognitiveVideo";
import type { CognitiveVideoProps } from "./types";

const DEFAULT_STORYBOARD: CognitiveVideoProps["storyboard"] = {
  style: "cognitive_explainer",
  series: "认知提升",
  episode: "01",
  title: "中产退场 低欲生活才是赢家",
  fps: 30,
  width: 1920,
  height: 1080,
  duration_sec: 60,
  duration_in_frames: 1800,
  transition_frames: 8,
  narration: "narration.wav",
  narration_volume: 0.85,
  bgm: "ambient_bgm.wav",
  bgm_volume: 0.12,
  hook: {
    text_zh: "去换个活法吧！当局者困在围城，局外者活成神仙",
    duration_sec: 2.8,
  },
  series_badge: {
    series: "认知提升",
    episode: "01",
    duration_sec: 4.3,
  },
  subtitles: [],
  subtitle_style: {
    zh_size: 36,
    margin_bottom: 200,
    color_zh: "#ffffff",
  },
  emphasis: [],
  emphasis_style: {
    font_size: 52,
    color: "#ffe8b0",
  },
  grade: {
    warmth: 0.35,
  },
  shots: [],
  closing_title: {
    text_zh: "建议收藏，换个活法",
    appear_at_sec: 56,
    duration_sec: 4,
  },
  tags: ["自我成长", "人性洞察"],
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="CognitiveVideo"
      component={CognitiveVideo}
      durationInFrames={DEFAULT_STORYBOARD.duration_in_frames}
      fps={DEFAULT_STORYBOARD.fps}
      width={DEFAULT_STORYBOARD.width}
      height={DEFAULT_STORYBOARD.height}
      defaultProps={{
        storyboard: DEFAULT_STORYBOARD,
      } satisfies CognitiveVideoProps}
      calculateMetadata={calculateCognitiveMetadata}
    />
  );
};
