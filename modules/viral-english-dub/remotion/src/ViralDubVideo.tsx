import { AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile } from "remotion";
import { BilingualSubtitle } from "./BilingualSubtitle";
import { HookTitle } from "./HookTitle";
import { SubtitleMask } from "./SubtitleMask";
import type { StoryboardData, VideoPiece, ViralDubVideoProps } from "./types";

const toFrames = (sec: number, fps: number) => Math.max(1, Math.round(sec * fps));

const RetimedSourceVideo: React.FC<{
  sourceVideo: string;
  pieces: VideoPiece[];
  fps: number;
}> = ({ sourceVideo, pieces, fps }) => {
  return (
    <>
      {pieces.map((piece, index) => {
        const from = Math.round(piece.out_start_sec * fps);
        const durationInFrames = toFrames(piece.out_duration_sec, fps);
        const startFrom = Math.round(piece.src_start_sec * fps);
        const rate = Math.max(0.1, Math.min(4, piece.playback_rate || 1));
        return (
          <Sequence key={`vp-${index}`} from={from} durationInFrames={durationInFrames} layout="none">
            <OffthreadVideo
              src={staticFile(sourceVideo)}
              startFrom={startFrom}
              playbackRate={rate}
              muted
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </Sequence>
        );
      })}
    </>
  );
};

const SourceVideoLayer: React.FC<{ storyboard: StoryboardData }> = ({ storyboard }) => {
  const pieces = storyboard.video_pieces ?? [];
  if (pieces.length > 0) {
    return (
      <RetimedSourceVideo
        sourceVideo={storyboard.source_video}
        pieces={pieces}
        fps={storyboard.fps}
      />
    );
  }
  return (
    <OffthreadVideo
      src={staticFile(storyboard.source_video)}
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
      volume={0}
    />
  );
};

export const ViralDubVideo: React.FC<ViralDubVideoProps> = ({ storyboard }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <SourceVideoLayer storyboard={storyboard} />

      {storyboard.hide_original_subtitles !== false ? (
        <SubtitleMask
          mask={storyboard.subtitle_mask ?? {}}
          width={storyboard.width}
          height={storyboard.height}
          segments={storyboard.subtitles}
        />
      ) : null}

      {storyboard.show_hook_title ? <HookTitle hook={storyboard.hook} /> : null}

      {storyboard.show_subtitles !== false ? (
        <BilingualSubtitle
          segments={storyboard.subtitles}
          styleConfig={storyboard.subtitle_style}
        />
      ) : null}

      {storyboard.narration ? (
        <Audio src={staticFile(storyboard.narration)} volume={storyboard.narration_volume ?? 0.92} />
      ) : null}
      {storyboard.bgm ? (
        <Audio src={staticFile(storyboard.bgm)} volume={storyboard.bgm_volume ?? 0.08} />
      ) : null}
    </AbsoluteFill>
  );
};

export const calculateViralDubMetadata = async ({ props }: { props: ViralDubVideoProps }) => {
  const fps = props.storyboard.fps;
  return {
    durationInFrames: props.storyboard.duration_in_frames,
    fps,
    width: props.storyboard.width,
    height: props.storyboard.height,
  };
};
