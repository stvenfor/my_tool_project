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

export const STICKMAN_LINE = "#111111";
export const STICKMAN_ACCENT = "#2f6fed";
