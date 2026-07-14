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
import { DataCard } from "./DataCard";
import { CreamVignette, FilmGrain } from "./FilmGrain";
import { KenBurns, SoftTransition } from "./SoftTransition";
import { getTotalFrames, resolveShots } from "./resolveShots";
import type { CityHealingVideoProps } from "./types";

const CutMedia: React.FC<{
  src: string;
  isImage: boolean;
  fps: number;
}> = ({ src, isImage, fps }) => {
  if (isImage) {
    return (
      <Img
        src={staticFile(src)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      />
    );
  }

  return (
    <OffthreadVideo
      src={staticFile(src)}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
      }}
      playbackRate={1}
      startFrom={0}
    />
  );
};

const ClosingTitle: React.FC<{
  text: string;
  appearAtSec: number;
  durationSec: number;
}> = ({ text, appearAtSec, durationSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const start = Math.round(appearAtSec * fps);
  const end = Math.round((appearAtSec + durationSec) * fps);
  const opacity = interpolate(frame, [start, start + fps, end - fps, end], [0, 1, 1, 0], {
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
        paddingBottom: 120,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          opacity,
          fontSize: 42,
          fontWeight: 600,
          color: "#fff6e8",
          letterSpacing: "0.12em",
          textShadow: "0 2px 16px rgba(60, 40, 20, 0.45)",
        }}
      >
        {text}
      </div>
      <div
        style={{
          opacity: opacity * 0.8,
          marginTop: 12,
          fontSize: 16,
          color: "#e8d4b8",
          letterSpacing: "0.2em",
        }}
      >
        等你来慢慢遇见
      </div>
    </AbsoluteFill>
  );
};

export const CityHealingVideo: React.FC<CityHealingVideoProps> = ({ storyboard }) => {
  const { fps } = useVideoConfig();
  const shots = resolveShots(storyboard, fps);
  const transitionFrames = storyboard.transition_frames ?? 12;

  return (
    <AbsoluteFill style={{ backgroundColor: "#1a1410" }}>
      {shots.map((shot, index) => (
        <Sequence
          key={`${shot.id}-${index}`}
          from={shot.fromFrame}
          durationInFrames={shot.durationInFrames}
          premountFor={fps}
        >
          <SoftTransition
            durationInFrames={shot.durationInFrames}
            transitionFrames={transitionFrames}
          >
            <KenBurns enabled={shot.is_image} durationInFrames={shot.durationInFrames}>
              <CutMedia src={shot.src} isImage={shot.is_image} fps={fps} />
            </KenBurns>
          </SoftTransition>
        </Sequence>
      ))}

      {storyboard.data_cards.map((card) => (
        <DataCard key={card.id} card={card} />
      ))}

      <ClosingTitle
        text={storyboard.closing_title.text}
        appearAtSec={storyboard.closing_title.appear_at_sec}
        durationSec={storyboard.closing_title.duration_sec}
      />

      <CreamVignette />
      <FilmGrain />

      {storyboard.narration ? (
        <Audio src={staticFile(storyboard.narration)} volume={1} />
      ) : null}
      {storyboard.bgm ? (
        <Audio src={staticFile(storyboard.bgm)} volume={storyboard.bgm_volume ?? 0.12} />
      ) : null}
    </AbsoluteFill>
  );
};

export const calculateCityHealingMetadata = async ({
  props,
}: {
  props: CityHealingVideoProps;
}) => {
  const fps = props.storyboard.fps;
  return {
    durationInFrames: getTotalFrames(props.storyboard, fps),
    fps,
    width: props.storyboard.width,
    height: props.storyboard.height,
  };
};
