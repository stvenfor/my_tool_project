export type StoryboardShot = {
  id: string;
  clip: string;
  is_image?: boolean;
  start_sec: number;
  duration_sec: number;
  phase?: string;
  transition?: string;
};

export type SubtitleSegment = {
  start_sec: number;
  duration_sec: number;
  en: string;
  zh: string;
};

export type SubtitleStyle = {
  mode?: string;
  position?: string;
  zh_size?: number;
  en_size?: number;
  margin_bottom?: number;
  margin_top?: number;
  color_zh?: string;
  color_en?: string;
  shadow?: string;
};

export type HookConfig = {
  text_zh: string;
  text_en?: string;
  duration_sec: number;
};

export type ThreeKingdomsStoryboard = {
  style: string;
  series_title?: string;
  episode_title?: string;
  episode_hook?: string;
  fps: number;
  width: number;
  height: number;
  duration_sec: number;
  duration_in_frames: number;
  transition_frames?: number;
  narration?: string;
  narration_volume?: number;
  bgm?: string;
  bgm_volume?: number;
  hook: HookConfig;
  subtitles: SubtitleSegment[];
  subtitle_style: SubtitleStyle;
  shots: StoryboardShot[];
  closing_title: {
    text_zh: string;
    text_en: string;
    appear_at_sec: number;
    duration_sec: number;
  };
};

export type StoryboardData = ThreeKingdomsStoryboard;

export type ThreeKingdomsEnglishVideoProps = {
  storyboard: ThreeKingdomsStoryboard;
};

export type ResolvedShot = StoryboardShot & {
  fromFrame: number;
  durationInFrames: number;
  src: string;
  is_image: boolean;
};
