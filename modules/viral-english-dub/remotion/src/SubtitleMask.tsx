import { useCurrentFrame, useVideoConfig } from "remotion";
import type { SubtitleMaskConfig, SubtitleSegment } from "./types";

type SubtitleMaskProps = {
  mask: SubtitleMaskConfig;
  width: number;
  height: number;
  segments?: SubtitleSegment[];
};

/**
 * Cover original hard-coded captions without a thick black band.
 * Center cover is a text-height soft strip during dialogue only.
 */
export const SubtitleMask: React.FC<SubtitleMaskProps> = ({ mask, height, segments = [] }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentSec = frame / fps;

  const topPct = mask.top_pct ?? 0;
  const bottomPct = mask.bottom_pct ?? 0;
  const topHeight = Math.round(height * topPct);
  const bottomHeight = Math.round(height * bottomPct);
  const color = mask.color ?? "#000000";

  const centerStartPct = mask.center_start_pct;
  const centerEndPct = mask.center_end_pct;
  const bandPct =
    centerStartPct != null && centerEndPct != null ? centerEndPct - centerStartPct : 0;
  const hasCenterBand =
    centerStartPct != null &&
    centerEndPct != null &&
    bandPct > 0 &&
    bandPct <= 0.12;

  const active = hasCenterBand
    ? segments.find(
        (seg) => currentSec >= seg.start_sec && currentSec < seg.start_sec + seg.duration_sec,
      )
    : null;

  const centerVisible = Boolean(active && hasCenterBand);
  const centerTop = hasCenterBand ? Math.round(height * (centerStartPct as number)) : 0;
  const centerHeight = hasCenterBand
    ? Math.round(height * ((centerEndPct as number) - (centerStartPct as number)))
    : 0;

  return (
    <>
      {topHeight > 0 ? (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: topHeight,
            background: color,
            pointerEvents: "none",
          }}
        />
      ) : null}
      {bottomHeight > 0 ? (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: bottomHeight,
            background: color,
            pointerEvents: "none",
          }}
        />
      ) : null}
      {centerVisible ? (
        <div
          style={{
            position: "absolute",
            top: centerTop,
            left: "18%",
            right: "18%",
            height: Math.max(28, Math.min(72, centerHeight)),
            background: "rgba(30,28,26,0.42)",
            backdropFilter: "blur(14px)",
            WebkitBackdropFilter: "blur(14px)",
            borderRadius: 8,
            pointerEvents: "none",
          }}
        />
      ) : null}
    </>
  );
};
