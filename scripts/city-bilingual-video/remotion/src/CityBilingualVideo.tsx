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
import type { CityBilingualVideoProps } from "./types";

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
  const scale = interpolate(frame, [start, start + 16], [1.08, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lineWidth = interpolate(frame, [start + 8, start + 24], [0, 100], {
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
        paddingBottom: 220,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
          padding: "20px 32px",
          borderRadius: 16,
          background: "linear-gradient(180deg, rgba(8,8,12,0.5) 0%, rgba(8,8,12,0.7) 100%)",
          border: "1px solid rgba(255,236,200,0.16)",
          backdropFilter: "blur(6px)",
          opacity,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            width: lineWidth,
            height: 2,
            background: "linear-gradient(90deg, transparent, #f0d8a8, transparent)",
          }}
        />
        <div
          style={{
            fontSize: 40,
            fontWeight: 700,
            color: "#fff6e8",
            letterSpacing: "0.12em",
            textShadow: "0 0 20px rgba(240,216,168,0.4), 0 2px 16px rgba(0,0,0,0.55)",
            WebkitTextStroke: "0.5px rgba(0,0,0,0.35)",
          }}
        >
          {textZh}
        </div>
        <div
          style={{
            fontSize: 20,
            color: "#f0d8a8",
            letterSpacing: "0.08em",
            opacity: opacity * 0.9,
          }}
        >
          {textEn}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const CityBilingualVideo: React.FC<CityBilingualVideoProps> = ({ storyboard }) => {
  const { fps } = useVideoConfig();
  const shots = resolveShots(storyboard, fps);
  const transitionFrames = storyboard.transition_frames ?? 10;
  const overlapFrames = Math.max(4, Math.min(transitionFrames, 12));

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0806" }}>
      {shots.map((shot, index) => {
        const leadIn = index > 0 ? overlapFrames : 0;
        const fromFrame = Math.max(0, shot.fromFrame - leadIn);
        const durationInFrames = shot.durationInFrames + leadIn;

        return (
          <Sequence
            key={`${shot.id}-${index}`}
            from={fromFrame}
            durationInFrames={durationInFrames}
            premountFor={fps * 2}
          >
            <CinematicTransition
              durationInFrames={durationInFrames}
              transitionFrames={transitionFrames}
            >
              <CutMedia src={shot.src} isImage={shot.is_image} />
            </CinematicTransition>
          </Sequence>
        );
      })}

      <HookTitle hook={storyboard.hook} />
      <BilingualSubtitle
        segments={storyboard.subtitles}
        styleConfig={storyboard.subtitle_style}
      />
      <ClosingTitle
        textZh={storyboard.closing_title.text_zh}
        textEn={storyboard.closing_title.text_en}
        appearAtSec={storyboard.closing_title.appear_at_sec}
        durationSec={storyboard.closing_title.duration_sec}
      />

      {storyboard.narration ? (
        <Audio src={staticFile(storyboard.narration)} volume={storyboard.narration_volume ?? 0.55} />
      ) : null}
      {storyboard.bgm ? (
        <Audio src={staticFile(storyboard.bgm)} volume={storyboard.bgm_volume ?? 0.08} />
      ) : null}
    </AbsoluteFill>
  );
};

export const calculateCityBilingualMetadata = async ({
  props,
}: {
  props: CityBilingualVideoProps;
}) => {
  const fps = props.storyboard.fps;
  return {
    durationInFrames: getTotalFrames(props.storyboard, fps),
    fps,
    width: props.storyboard.width,
    height: props.storyboard.height,
  };
};
