export type StoryboardShot = {
  id: string;
  clip: string;
  is_image: boolean;
  start_sec: number;
  duration_sec: number;
  phase?: string;
  transition?: string;
  stickman_scene?: StickmanSceneConfig;
};

export type StickmanPose =
  | "desk_stress"
  | "thinking"
  | "crossroads"
  | "walk_relaxed"
  | "on_platform"
  | "crown_scroll"
  | "wave";

export type StickmanProp =
  | "laptop"
  | "city_silhouette"
  | "signpost"
  | "tree"
  | "wooden_stage"
  | "scroll_work"
  | "heart"
  | "none";

export type StickmanSceneConfig = {
  pose: StickmanPose;
  prop: StickmanProp;
  watermark?: string;
  scene_title?: string;
  headline?: string;
  extras?: string[];
  philosophy_quote?: string;
};

export type StickmanStyleConfig = {
  watermark?: string;
  disclaimer?: string;
  series_title?: string;
};

export type SubtitleSegment = {
  start_sec: number;
  duration_sec: number;
  zh: string;
  speaker?: string;
  character_key?: string;
  emphasis?: string[];
  visual_keyword?: string;
  phase?: string;
  id?: string;
};

export type EmphasisItem = {
  text: string;
  start_sec: number;
  duration_sec: number;
  phase?: string;
};

export type SubtitleStyle = {
  mode?: string;
  position?: string;
  zh_size?: number;
  margin_bottom?: number;
  color_zh?: string;
  shadow?: string;
};

export type EmphasisStyle = {
  font_size?: number;
  color?: string;
  position?: string;
};

export type GradeStyle = {
  warmth?: number;
  contrast?: number;
  vignette?: number;
};

export type HookConfig = {
  text_zh: string;
  duration_sec: number;
};

export type SeriesBadgeConfig = {
  series: string;
  episode: string;
  duration_sec: number;
};

export type ClosingTitle = {
  text_zh: string;
  appear_at_sec: number;
  duration_sec: number;
};

export type StoryboardData = {
  style: string;
  visual_style?: "cinematic" | "stickman";
  stickman?: StickmanStyleConfig;
  series: string;
  episode: string;
  title: string;
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
  series_badge: SeriesBadgeConfig;
  subtitles: SubtitleSegment[];
  subtitle_style: SubtitleStyle;
  emphasis: EmphasisItem[];
  emphasis_style: EmphasisStyle;
  grade: GradeStyle;
  shots: StoryboardShot[];
  closing_title: ClosingTitle;
  tags?: string[];
};

export type CognitiveVideoProps = {
  storyboard: StoryboardData;
};

export type ResolvedShot = StoryboardShot & {
  fromFrame: number;
  durationInFrames: number;
  src: string;
};
