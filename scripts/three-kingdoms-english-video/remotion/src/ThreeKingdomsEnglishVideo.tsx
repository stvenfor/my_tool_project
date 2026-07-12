import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { BilingualSubtitle } from "./BilingualSubtitle";
import { CinematicTransition } from "./CinematicTransition";
import { HookTitle } from "./HookTitle";
import { getTotalFrames, resolveShots } from "./resolveShots";
import type { ThreeKingdomsEnglishVideoProps } from "./types";

const CutMedia: React.FC<{ src: string; isImage: boolean }> = ({ src, isImage }) => {
  if (isImage) {
    return <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />;
  }
  return (
    <OffthreadVideo
      src={staticFile(src)}
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
      playbackRate={1}
      startFrom={0}
    />
  );
};

const ClosingTitle: React.FC<{
  textZh: string;
  textEn: string;
  appearAtSec: number;
  durationSec: number;
}> = ({ textZh, textEn, appearAtSec, durationSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const start = Math.round(appearAtSec * fps);
  const end = Math.round((appearAtSec + durationSec) * fps);
  const opacity = interpolate(frame, [start, start + 12, end - 12, end], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (frame < start || frame > end) return null;

  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 160, pointerEvents: "none" }}>
      <div style={{ opacity, textAlign: "center", padding: "16px 28px", background: "rgba(0,0,0,0.45)", borderRadius: 16 }}>
        <div style={{ fontSize: 36, fontWeight: 700, color: "#fff6e8", letterSpacing: "0.1em" }}>{textZh}</div>
        <div style={{ fontSize: 18, color: "#f0d8a8", marginTop: 8 }}>{textEn}</div>
      </div>
    </AbsoluteFill>
  );
};

export const ThreeKingdomsEnglishVideo: React.FC<ThreeKingdomsEnglishVideoProps> = ({ storyboard }) => {
  const { fps } = useVideoConfig();
  const shots = resolveShots(storyboard, fps);
  const transitionFrames = storyboard.transition_frames ?? 8;
  const overlapFrames = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#1a1208" }}>
      {shots.map((shot, index) => {
        const leadIn = index > 0 ? overlapFrames : 0;
        const fromFrame = Math.max(0, shot.fromFrame - leadIn);
        const durationInFrames = shot.durationInFrames + leadIn;
        return (
          <Sequence key={`${shot.id}-${index}`} from={fromFrame} durationInFrames={durationInFrames} premountFor={fps * 2}>
            <CinematicTransition durationInFrames={durationInFrames} transitionFrames={transitionFrames}>
              <CutMedia src={shot.src} isImage={shot.is_image} />
            </CinematicTransition>
          </Sequence>
        );
      })}

      <HookTitle hook={storyboard.hook} seriesTitle={storyboard.series_title} />
      <BilingualSubtitle segments={storyboard.subtitles} styleConfig={storyboard.subtitle_style} />
      <ClosingTitle
        textZh={storyboard.closing_title.text_zh}
        textEn={storyboard.closing_title.text_en}
        appearAtSec={storyboard.closing_title.appear_at_sec}
        durationSec={storyboard.closing_title.duration_sec}
      />

      {storyboard.narration ? (
        <Audio src={staticFile(storyboard.narration)} volume={storyboard.narration_volume ?? 0.85} />
      ) : null}
      {storyboard.bgm ? <Audio src={staticFile(storyboard.bgm)} volume={storyboard.bgm_volume ?? 0.25} /> : null}
    </AbsoluteFill>
  );
};

export const calculateThreeKingdomsMetadata = async ({ props }: { props: ThreeKingdomsEnglishVideoProps }) => {
  const fps = props.storyboard.fps;
  return {
    durationInFrames: getTotalFrames(props.storyboard, fps),
    fps,
    width: props.storyboard.width,
    height: props.storyboard.height,
  };
};
