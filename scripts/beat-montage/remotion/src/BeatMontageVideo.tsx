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
import type { BeatMontageVideoProps } from "./types";
import { getTotalFrames, resolveCuts } from "./resolveCuts";

const FlashOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 1, 2], [0, 0.85, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#ffffff",
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

const ZoomWrapper: React.FC<{ children: React.ReactNode; enabled: boolean }> = ({
  children,
  enabled,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const scale = enabled
    ? interpolate(frame, [0, durationInFrames], [1.05, 1.0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;

  return (
    <AbsoluteFill
      style={{
        transform: `scale(${scale})`,
        transformOrigin: "center center",
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

const CutMedia: React.FC<{
  src: string;
  isImage: boolean;
  trimIn: number;
  playbackRate: number;
  fps: number;
}> = ({ src, isImage, trimIn, playbackRate, fps }) => {
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
      startFrom={Math.round(trimIn * fps)}
      playbackRate={playbackRate}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
      }}
    />
  );
};

export const BeatMontageVideo: React.FC<BeatMontageVideoProps> = ({ montage }) => {
  const { fps } = useVideoConfig();
  const cuts = resolveCuts(montage, fps);
  const playbackRate = montage.playbackRate ?? 1.0;
  const audioSrc = montage.audio.startsWith("bgm/")
    ? montage.audio
    : `bgm/${montage.audio.replace(/^bgm\//, "")}`;

  return (
    <AbsoluteFill style={{ backgroundColor: "#050505" }}>
      {cuts.map((cut, index) => (
        <Sequence
          key={`${cut.clipId ?? cut.clip}-${index}`}
          from={cut.fromFrame}
          durationInFrames={cut.durationInFrames}
          premountFor={fps}
        >
          <ZoomWrapper enabled={cut.fx.includes("zoom")}>
            <CutMedia
              src={cut.src}
              isImage={cut.isImage}
              trimIn={cut.trimIn}
              playbackRate={playbackRate}
              fps={fps}
            />
          </ZoomWrapper>
          {cut.fx.includes("flash") ? <FlashOverlay /> : null}
        </Sequence>
      ))}

      <Audio src={staticFile(audioSrc)} volume={1} playbackRate={playbackRate} />
    </AbsoluteFill>
  );
};

export const calculateMontageMetadata = async ({
  props,
}: {
  props: BeatMontageVideoProps;
}) => {
  const fps = props.montage.fps;
  return {
    durationInFrames: getTotalFrames(props.montage, fps),
    fps,
    width: props.montage.width,
    height: props.montage.height,
  };
};
