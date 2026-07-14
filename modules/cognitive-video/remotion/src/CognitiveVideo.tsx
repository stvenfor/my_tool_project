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
import { CinematicTransition } from "./CinematicTransition";
import { HookTitle } from "./HookTitle";
import { KineticPhrase } from "./KineticPhrase";
import { SeriesBadge } from "./SeriesBadge";
import { SubtitleTrack } from "./SubtitleTrack";
import { StickmanScene } from "./stickman/StickmanScene";
import { StickmanEndCard } from "./stickman/StickmanEndCard";
import { getTotalFrames, resolveShots } from "./resolveShots";
import type { CognitiveVideoProps, StickmanSceneConfig } from "./types";

const CutMedia: React.FC<{
  src: string;
  isImage: boolean;
}> = ({ src, isImage }) => {
  if (isImage) {
    return (
      <Img
        src={staticFile(src)}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    );
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
  appearAtSec: number;
  durationSec: number;
}> = ({ textZh, appearAtSec, durationSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const start = Math.round(appearAtSec * fps);
  const end = Math.round((appearAtSec + durationSec) * fps);
  const opacity = interpolate(frame, [start, start + 12, end - 12, end], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [start, start + 16], [1.08, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (frame < start || frame > end) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 280,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          padding: "20px 36px",
          borderRadius: 16,
          background: "linear-gradient(180deg, rgba(8,8,12,0.5) 0%, rgba(8,8,12,0.7) 100%)",
          border: "1px solid rgba(255,236,200,0.16)",
          opacity,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            fontSize: 38,
            fontWeight: 700,
            color: "#fff6e8",
            letterSpacing: "0.12em",
            textShadow: "0 0 20px rgba(240,216,168,0.4), 0 2px 16px rgba(0,0,0,0.55)",
          }}
        >
          {textZh}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const CognitiveVideo: React.FC<CognitiveVideoProps> = ({ storyboard }) => {
  const { fps } = useVideoConfig();
  const shots = resolveShots(storyboard, fps);
  const transitionFrames = storyboard.transition_frames ?? 8;
  const overlapFrames = Math.max(4, Math.min(transitionFrames, 10));
  const isStickman = storyboard.visual_style === "stickman";
  const stickmanSeriesTitle =
    storyboard.stickman?.series_title ?? `${storyboard.series}${storyboard.episode}`;

  return (
    <AbsoluteFill style={{ backgroundColor: isStickman ? "#ffffff" : "#0a0806" }}>
      {shots.map((shot, index) => {
        const leadIn = index > 0 ? overlapFrames : 0;
        const fromFrame = Math.max(0, shot.fromFrame - leadIn);
        const durationInFrames = shot.durationInFrames + leadIn;
        const stickmanScene = shot.stickman_scene as StickmanSceneConfig | undefined;

        return (
          <Sequence
            key={`${shot.id}-${index}`}
            from={fromFrame}
            durationInFrames={durationInFrames}
            premountFor={isStickman ? 0 : fps * 2}
          >
            {isStickman && stickmanScene ? (
              <StickmanScene
                scene={stickmanScene}
                seriesTitle={stickmanSeriesTitle}
                disclaimer={storyboard.stickman?.disclaimer}
                phase={shot.phase}
                isFirstShot={index === 0}
                isClosingHold={index === shots.length - 1}
              />
            ) : (
              <CinematicTransition
                durationInFrames={durationInFrames}
                transitionFrames={transitionFrames}
              >
                <CutMedia src={shot.src} isImage={shot.is_image} />
              </CinematicTransition>
            )}
          </Sequence>
        );
      })}

      {!isStickman ? <SeriesBadge badge={storyboard.series_badge} /> : null}
      {!isStickman ? <HookTitle hook={storyboard.hook} /> : null}
      {!isStickman ? (
        <KineticPhrase items={storyboard.emphasis} styleConfig={storyboard.emphasis_style} />
      ) : null}
      <SubtitleTrack
        segments={storyboard.subtitles}
        styleConfig={storyboard.subtitle_style}
        visualStyle={storyboard.visual_style}
      />
      {isStickman ? (
        <StickmanEndCard
          textZh={storyboard.closing_title.text_zh}
          appearAtSec={storyboard.closing_title.appear_at_sec}
          durationSec={storyboard.closing_title.duration_sec}
        />
      ) : (
        <ClosingTitle
          textZh={storyboard.closing_title.text_zh}
          appearAtSec={storyboard.closing_title.appear_at_sec}
          durationSec={storyboard.closing_title.duration_sec}
        />
      )}

      {storyboard.narration ? (
        <Audio src={staticFile(storyboard.narration)} volume={storyboard.narration_volume ?? 0.85} />
      ) : null}
      {storyboard.bgm ? (
        <Audio src={staticFile(storyboard.bgm)} volume={storyboard.bgm_volume ?? 0.12} />
      ) : null}
    </AbsoluteFill>
  );
};

export const calculateCognitiveMetadata = async ({
  props,
}: {
  props: CognitiveVideoProps;
}) => {
  const fps = props.storyboard.fps;
  return {
    durationInFrames: getTotalFrames(props.storyboard, fps),
    fps,
    width: props.storyboard.width,
    height: props.storyboard.height,
  };
};
