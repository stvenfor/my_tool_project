import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { StickmanSceneConfig } from "./poses";
import { StickmanDecorations } from "./StickmanDecorations";
import { StickmanFigure } from "./StickmanFigure";
import { StickmanSceneBackground } from "./StickmanSceneBackground";
import { themeForPhase } from "./theme";
import { useVideoLayout } from "../useVideoLayout";

type StickmanSceneProps = {
  scene: StickmanSceneConfig;
  seriesTitle: string;
  disclaimer?: string;
  phase?: string;
  isFirstShot?: boolean;
  isClosingHold?: boolean;
};

const StickmanSvg: React.FC<{
  scene: StickmanSceneConfig;
  extras: string[];
  theme: ReturnType<typeof themeForPhase>;
  floatY: number;
  svgRotate: number;
  isLandscape: boolean;
}> = ({ scene, extras, theme, floatY, svgRotate, isLandscape }) => (
  <svg
    viewBox="0 0 420 380"
    style={{
      position: isLandscape ? "relative" : "absolute",
      left: isLandscape ? undefined : "50%",
      top: isLandscape ? undefined : "54%",
      width: isLandscape ? "100%" : "90%",
      maxWidth: isLandscape ? 760 : 900,
      height: "auto",
      transform: isLandscape
        ? `translateY(${floatY}px) rotate(${svgRotate}deg)`
        : `translate(-50%, -50%) translateY(${floatY}px) rotate(${svgRotate}deg)`,
    }}
  >
    <StickmanDecorations extras={extras} theme={theme} />
    <StickmanFigure pose={scene.pose} prop={scene.prop} />
  </svg>
);

export const StickmanScene: React.FC<StickmanSceneProps> = ({
  scene,
  seriesTitle,
  disclaimer = "个人观点，无不良引导",
  phase = "insight",
  isFirstShot = false,
  isClosingHold = false,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const layout = useVideoLayout();
  const theme = themeForPhase(phase);
  const philosophy = (scene.philosophy_quote ?? "").slice(0, 8);
  const headline = scene.headline ?? "";
  const extras = scene.extras ?? [];

  const holdStart = isClosingHold ? Math.max(0, durationInFrames - Math.round(fps * 2.2)) : durationInFrames;
  const inHold = isClosingHold && frame >= holdStart;

  const enter = spring({
    frame: isFirstShot ? frame : frame,
    fps,
    config: { damping: 16, stiffness: 140, mass: 0.7 },
  });
  const cardScale = 0.94 + enter * 0.06;
  const cardY = (1 - enter) * (layout.isLandscape ? 16 : 28);
  const headlinePop = spring({
    frame: frame - 4,
    fps,
    config: { damping: 12, stiffness: 180 },
  });
  const floatY = inHold ? 0 : interpolate(Math.sin(frame / (fps * 1.05)), [-1, 1], [-6, 6]);
  const svgRotate = inHold ? 0 : interpolate(Math.sin(frame / (fps * 2.4)), [-1, 1], [-1.2, 1.2]);

  const headlineBlock = headline ? (
    <div
      style={{
        textAlign: layout.isLandscape ? "left" : "center",
        fontSize: layout.headlineSize,
        fontWeight: 800,
        color: theme.accent,
        letterSpacing: "0.06em",
        transform: layout.isLandscape
          ? `scale(${0.92 + headlinePop * 0.08}) translateX(${(1 - headlinePop) * -12}px)`
          : `scale(${0.88 + headlinePop * 0.12}) translateY(${(1 - headlinePop) * 12}px)`,
        padding: layout.isLandscape ? "0 8px 0 0" : "0 32px",
        textShadow: `0 2px 16px ${theme.accentSoft}`,
        opacity: headlinePop,
        lineHeight: 1.25,
      }}
    >
      {headline}
    </div>
  ) : null;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <StickmanSceneBackground theme={theme} />

      <div
        style={{
          height: layout.headerHeight,
          borderBottom: "1.5px solid rgba(17,17,17,0.12)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: layout.isLandscape ? "0 28px" : "0 36px",
          flexShrink: 0,
          position: "relative",
          background: "rgba(255,255,255,0.72)",
          backdropFilter: "blur(8px)",
          zIndex: 3,
        }}
      >
        {philosophy ? (
          <div
            style={{
              position: "absolute",
              top: layout.isLandscape ? 8 : 12,
              left: layout.isLandscape ? 20 : 24,
              fontSize: layout.philosophySize,
              fontWeight: 800,
              color: theme.accent,
              letterSpacing: "0.1em",
              padding: "4px 12px",
              borderRadius: 8,
              background: theme.accentSoft,
              maxWidth: 240,
              whiteSpace: "nowrap",
              overflow: "hidden",
              transform: `translateY(${(1 - enter) * -8}px)`,
              opacity: enter,
            }}
          >
            {philosophy}
          </div>
        ) : null}

        <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: philosophy ? (layout.isLandscape ? 18 : 26) : 0 }}>
          <div
            style={{
              width: layout.isLandscape ? 32 : 36,
              height: layout.isLandscape ? 32 : 36,
              borderRadius: "50%",
              background: `linear-gradient(135deg, ${theme.accent} 0%, #8b5cf6 100%)`,
              border: "2px solid rgba(17,17,17,0.85)",
              boxShadow: `0 4px 14px ${theme.accentSoft}`,
              flexShrink: 0,
            }}
          />
          <div
            style={{
              fontSize: layout.seriesTitleSize,
              fontWeight: 700,
              color: "#111",
              letterSpacing: "0.04em",
            }}
          >
            {seriesTitle}
          </div>
        </div>
        <div style={{ fontSize: layout.isLandscape ? 16 : 18, color: "#888", letterSpacing: "0.02em", flexShrink: 0 }}>
          {disclaimer}
        </div>
      </div>

      <div
        style={{
          flex: 1,
          position: "relative",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: layout.isLandscape ? "16px 24px 12px" : "24px 28px 16px",
          zIndex: 2,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            borderRadius: layout.isLandscape ? 22 : 28,
            background: theme.cardBg,
            border: "1.5px solid rgba(17,17,17,0.08)",
            boxShadow: "0 16px 48px rgba(17,17,17,0.08), inset 0 1px 0 rgba(255,255,255,0.9)",
            position: "relative",
            overflow: "hidden",
            transform: `translateY(${cardY}px) scale(${cardScale})`,
            opacity: enter,
            display: layout.isLandscape ? "flex" : "block",
            flexDirection: layout.isLandscape ? "row" : undefined,
            alignItems: layout.isLandscape ? "center" : undefined,
          }}
        >
          {layout.isLandscape ? (
            <>
              <div
                style={{
                  flex: "0 0 38%",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  padding: "0 36px 0 40px",
                  zIndex: 2,
                }}
              >
                {headlineBlock}
              </div>
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "12px 24px 12px 0",
                  minHeight: 0,
                }}
              >
                <StickmanSvg
                  scene={scene}
                  extras={extras}
                  theme={theme}
                  floatY={floatY}
                  svgRotate={svgRotate}
                  isLandscape
                />
              </div>
            </>
          ) : (
            <>
              {headline ? (
                <div
                  style={{
                    position: "absolute",
                    top: 36,
                    left: 0,
                    right: 0,
                    zIndex: 2,
                  }}
                >
                  {headlineBlock}
                </div>
              ) : null}
              <StickmanSvg
                scene={scene}
                extras={extras}
                theme={theme}
                floatY={floatY}
                svgRotate={svgRotate}
                isLandscape={false}
              />
            </>
          )}
        </div>
      </div>

      <div
        style={{
          height: 6,
          background: `linear-gradient(90deg, ${theme.accent}, transparent)`,
          flexShrink: 0,
          opacity: 0.5,
        }}
      />
    </div>
  );
};
