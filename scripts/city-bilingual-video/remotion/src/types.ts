export type StoryboardShot = {
  id: string;
  clip: string;
  is_image: boolean;
  start_sec: number;
  duration_sec: number;
  phase?: "day" | "transition" | "night";
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
  color_zh?: string;
  color_en?: string;
  shadow?: string;
};

export type GradeStyle = {
  day_warmth?: number;
  night_warmth?: number;
  pivot_sec?: number;
};

export type HookConfig = {
  text_zh: string;
  duration_sec: number;
};

export type ClosingTitle = {
  text_zh: string;
  text_en: string;
  appear_at_sec: number;
  duration_sec: number;
};

export type StoryboardData = {
  style: string;
  city_name: string;
  ancient_name: string;
  fps: number;
  width: number;
  height: number;
  duration_sec: number;
  duration_in_frames: number;
  transition_frames: number;
  narration: string;
  narration_volume: number;
  bgm: string;
  bgm_volume: number;
  hook: HookConfig;
  subtitles: SubtitleSegment[];
  subtitle_style: SubtitleStyle;
  grade: GradeStyle;
  shots: StoryboardShot[];
  closing_title: ClosingTitle;
};

export type CityBilingualVideoProps = {
  storyboard: StoryboardData;
};

export type ResolvedShot = StoryboardShot & {
  fromFrame: number;
  durationInFrames: number;
  src: string;
};
