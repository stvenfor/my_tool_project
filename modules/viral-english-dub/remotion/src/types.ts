export type SubtitleSegment = {
  start_sec: number;
  duration_sec: number;
  en: string;
  zh: string;
  speaker_id?: string;
};

export type SubtitleStyle = {
  en_size?: number;
  zh_size?: number;
  margin_bottom?: number;
  position?: "bottom" | "center";
  color_en?: string;
  color_zh?: string;
  shadow?: string;
};

export type SubtitleMaskConfig = {
  top_pct?: number;
  bottom_pct?: number;
  center_start_pct?: number;
  center_end_pct?: number;
  color?: string;
};

export type HookConfig = {
  text_en: string;
  duration_sec: number;
};

export type VideoPiece = {
  kind?: "speech" | "gap";
  src_start_sec: number;
  src_end_sec: number;
  out_start_sec: number;
  out_duration_sec: number;
  playback_rate: number;
  index?: number;
};

export type StoryboardData = {
  style: string;
  clip_id: string;
  title: string;
  fps: number;
  width: number;
  height: number;
  duration_sec: number;
  duration_in_frames: number;
  source_video: string;
  video_pieces?: VideoPiece[];
  narration: string;
  narration_volume: number;
  bgm: string;
  bgm_volume: number;
  show_hook_title: boolean;
  show_subtitles?: boolean;
  hide_original_subtitles?: boolean;
  subtitle_mask?: SubtitleMaskConfig;
  hook: HookConfig;
  subtitles: SubtitleSegment[];
  subtitle_style: SubtitleStyle;
};

export type ViralDubVideoProps = {
  storyboard: StoryboardData;
};
