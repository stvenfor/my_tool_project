import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();
  const flicker = interpolate(frame % 4, [0, 2, 4], [0.04, 0.06, 0.04]);

  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        opacity: flicker,
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E\")",
        mixBlendMode: "soft-light",
      }}
    />
  );
};

export const CreamVignette: React.FC = () => (
  <AbsoluteFill
    style={{
      pointerEvents: "none",
      background:
        "radial-gradient(ellipse at center, rgba(255,248,235,0) 45%, rgba(120,90,60,0.18) 100%)",
    }}
  />
);
