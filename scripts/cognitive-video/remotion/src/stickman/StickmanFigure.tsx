import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { StickmanPose, StickmanProp } from "./poses";
import { STICKMAN_ACCENT, STICKMAN_LINE } from "./poses";
import { StickmanProps } from "./StickmanProps";

type StickmanFigureProps = {
  pose: StickmanPose;
  prop: StickmanProp;
};

const drawHead = (
  cx: number,
  cy: number,
  r: number,
  expression: "neutral" | "stress" | "smile",
  tilt = 0,
) => (
  <g transform={`rotate(${tilt}, ${cx}, ${cy})`}>
    <circle cx={cx} cy={cy} r={r} fill="#fff" stroke={STICKMAN_LINE} strokeWidth={3.2} />
    <circle cx={cx - 8} cy={cy - 2} r={2.2} fill={STICKMAN_LINE} />
    <circle cx={cx + 8} cy={cy - 2} r={2.2} fill={STICKMAN_LINE} />
    {expression === "stress" ? (
      <path
        d={`M ${cx - 10} ${cy + 12} Q ${cx} ${cy + 6} ${cx + 10} ${cy + 12}`}
        fill="none"
        stroke={STICKMAN_LINE}
        strokeWidth={2.5}
      />
    ) : expression === "smile" ? (
      <path
        d={`M ${cx - 10} ${cy + 10} Q ${cx} ${cy + 18} ${cx + 10} ${cy + 10}`}
        fill="none"
        stroke={STICKMAN_LINE}
        strokeWidth={2.5}
      />
    ) : (
      <line x1={cx - 8} y1={cy + 12} x2={cx + 8} y2={cy + 12} stroke={STICKMAN_LINE} strokeWidth={2.5} />
    )}
  </g>
);

export const StickmanFigure: React.FC<StickmanFigureProps> = ({ pose, prop }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const bob = interpolate(Math.sin(frame / (fps * 0.85)), [-1, 1], [-5, 5]);
  const armSwing = interpolate(Math.sin(frame / (fps * 0.65)), [-1, 1], [-16, 16]);
  const breathe = interpolate(Math.sin(frame / (fps * 1.2)), [-1, 1], [0.98, 1.02]);
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 130 } });
  const figureY = (1 - enter) * 30;
  const figureScale = 0.88 + enter * 0.12;

  const stroke = STICKMAN_LINE;
  const sw = 3.2;

  const wrap = (children: React.ReactNode, extraTransform = "") => (
    <g
      transform={`translate(0, ${bob + figureY}) scale(${figureScale * breathe}) ${extraTransform}`}
      opacity={enter}
    >
      {children}
    </g>
  );

  if (pose === "desk_stress") {
    const shake = interpolate(Math.sin(frame / (fps * 0.35)), [-1, 1], [-2, 2]);
    return wrap(
      <>
        <StickmanProps prop={prop} bob={shake * 0.5} frame={frame} fps={fps} />
        {drawHead(180, 168, 34, "stress", shake * 0.4)}
        <line x1={180} y1={202} x2={180} y2={268} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={220} x2={148 + shake} y2={248} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={220} x2={210} y2={236 + armSwing * 0.2} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={268} x2={156} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={268} x2={204} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={156} y1={320} x2={156} y2={340} stroke={stroke} strokeWidth={sw} />
        <line x1={204} y1={320} x2={204} y2={340} stroke={stroke} strokeWidth={sw} />
      </>,
      `translate(${shake}, 0)`,
    );
  }

  if (pose === "thinking") {
    const scratch = interpolate(Math.sin(frame / (fps * 0.5)), [-1, 1], [-8, 8]);
    return wrap(
      <>
        <StickmanProps prop={prop} bob={0} frame={frame} fps={fps} />
        {drawHead(190, 130, 36, "neutral", scratch * 0.15)}
        <line x1={190} y1={166} x2={190} y2={250} stroke={stroke} strokeWidth={sw} />
        <line x1={190} y1={190} x2={160 + scratch * 0.3} y2={170 + scratch * 0.2} stroke={stroke} strokeWidth={sw} />
        <line x1={160 + scratch * 0.3} y1={170 + scratch * 0.2} x2={152 + scratch} y2={148} stroke={stroke} strokeWidth={sw} />
        <line x1={190} y1={190} x2={220} y2={210} stroke={stroke} strokeWidth={sw} />
        <line x1={190} y1={250} x2={168} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={190} y1={250} x2={212} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={168} y1={320} x2={168} y2={340} stroke={stroke} strokeWidth={sw} />
        <line x1={212} y1={320} x2={212} y2={340} stroke={stroke} strokeWidth={sw} />
      </>,
    );
  }

  if (pose === "crossroads") {
    const look = interpolate(Math.sin(frame / (fps * 1.4)), [-1, 1], [-6, 6]);
    return wrap(
      <>
        <StickmanProps prop={prop} bob={0} frame={frame} fps={fps} />
        {drawHead(180 + look * 0.3, 140, 34, "neutral", look * 0.2)}
        <line x1={180} y1={174} x2={180} y2={252} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={200} x2={150 + look * 0.2} y2={228} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={200} x2={210 - look * 0.2} y2={228} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={252} x2={158} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={252} x2={202} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={158} y1={320} x2={158} y2={340} stroke={stroke} strokeWidth={sw} />
        <line x1={202} y1={320} x2={202} y2={340} stroke={stroke} strokeWidth={sw} />
      </>,
    );
  }

  if (pose === "walk_relaxed") {
    const legShift = armSwing * 0.75;
    return wrap(
      <>
        <StickmanProps prop={prop} bob={0} frame={frame} fps={fps} />
        {drawHead(180, 132, 34, "smile")}
        <line x1={180} y1={166} x2={180} y2={248} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={190} x2={180 + armSwing} y2={220} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={190} x2={180 - armSwing} y2={220} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={248} x2={168 + legShift} y2={318} stroke={stroke} strokeWidth={sw} />
        <line x1={180} y1={248} x2={192 - legShift} y2={318} stroke={stroke} strokeWidth={sw} />
        <line x1={168 + legShift} y1={318} x2={168 + legShift} y2={340} stroke={stroke} strokeWidth={sw} />
        <line x1={192 - legShift} y1={318} x2={192 - legShift} y2={340} stroke={stroke} strokeWidth={sw} />
      </>,
      `translate(${armSwing * 0.2}, 0)`,
    );
  }

  if (pose === "on_platform") {
    const wobble = interpolate(Math.sin(frame / (fps * 0.45)), [-1, 1], [-3, 3]);
    return wrap(
      <>
        <StickmanProps prop={prop} bob={wobble} frame={frame} fps={fps} />
        {drawHead(280, 210, 34, "smile", wobble * 0.3)}
        <rect x="262" y="238" width="36" height="44" rx="4" fill="#d8e4f0" stroke={stroke} strokeWidth={2.2} />
        <line x1={280} y1={244} x2={280} y2={282} stroke={stroke} strokeWidth={sw} />
        <line x1={280} y1={258} x2={258 + wobble} y2={272} stroke={stroke} strokeWidth={sw} />
        <line x1={280} y1={258} x2={302 - wobble} y2={272} stroke={stroke} strokeWidth={sw} />
        <line x1={280} y1={282} x2={268} y2={300} stroke={stroke} strokeWidth={sw} />
        <line x1={280} y1={282} x2={292} y2={300} stroke={stroke} strokeWidth={sw} />
      </>,
      `rotate(${wobble * 0.4}, 280, 300)`,
    );
  }

  if (pose === "crown_scroll") {
    const bounce = interpolate(Math.sin(frame / (fps * 0.55)), [-1, 1], [-3, 3]);
    return wrap(
      <>
        <StickmanProps prop={prop} bob={bounce} frame={frame} fps={fps} />
        <polygon
          points="166,118 176,98 186,118 196,98 206,118"
          fill="#f4c430"
          stroke={stroke}
          strokeWidth={2}
          transform={`translate(0, ${bounce})`}
        />
        {drawHead(186, 138 + bounce, 34, "smile")}
        <line x1={186} y1={172} x2={186} y2={252} stroke={stroke} strokeWidth={sw} />
        <line x1={186} y1={196} x2={160} y2={224} stroke={stroke} strokeWidth={sw} />
        <line x1={186} y1={196} x2={212 + armSwing * 0.25} y2={224} stroke={stroke} strokeWidth={sw} />
        <line x1={186} y1={252} x2={168} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={186} y1={252} x2={204} y2={320} stroke={stroke} strokeWidth={sw} />
        <line x1={168} y1={320} x2={168} y2={340} stroke={stroke} strokeWidth={sw} />
        <line x1={204} y1={320} x2={204} y2={340} stroke={stroke} strokeWidth={sw} />
      </>,
    );
  }

  return wrap(
    <>
      <StickmanProps prop={prop} bob={0} frame={frame} fps={fps} />
      {drawHead(190, 136, 36, "smile")}
      <line x1={190} y1={172} x2={190} y2={252} stroke={stroke} strokeWidth={sw} />
      <line x1={190} y1={196} x2={160} y2={176} stroke={stroke} strokeWidth={sw} />
      <line x1={190} y1={196} x2={220 + armSwing} y2={160 - armSwing * 0.5} stroke={stroke} strokeWidth={sw} />
      <line x1={190} y1={252} x2={172} y2={320} stroke={stroke} strokeWidth={sw} />
      <line x1={190} y1={252} x2={208} y2={320} stroke={stroke} strokeWidth={sw} />
      <line x1={172} y1={320} x2={172} y2={340} stroke={stroke} strokeWidth={sw} />
      <line x1={208} y1={320} x2={208} y2={340} stroke={stroke} strokeWidth={sw} />
      <circle cx={228 + armSwing * 0.4} cy={148 - armSwing * 0.2} r={5} fill={STICKMAN_ACCENT} opacity={0.9} />
    </>,
  );
};
