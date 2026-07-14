export type StoryboardShot = {
  id: string;
  clip: string;
  is_image: boolean;
  start_sec: number;
  duration_sec: number;
  transition_frames: number;
  zh_desc?: string;
};

export type DataCard = {
  id: string;
  label: string;
  value: number;
  unit: string;
  appear_at_sec: number;
  duration_sec: number;
};

export type ClosingTitle = {
  text: string;
  appear_at_sec: number;
  duration_sec: number;
};

export type StoryboardData = {
  city_name: string;
  fps: number;
  width: number;
  height: number;
  duration_sec: number;
  duration_in_frames: number;
  transition_frames: number;
  narration: string;
  bgm: string;
  bgm_volume: number;
  shots: StoryboardShot[];
  data_cards: DataCard[];
  closing_title: ClosingTitle;
};

export type CityHealingVideoProps = {
  storyboard: StoryboardData;
};

export type ResolvedShot = StoryboardShot & {
  fromFrame: number;
  durationInFrames: number;
  src: string;
};
