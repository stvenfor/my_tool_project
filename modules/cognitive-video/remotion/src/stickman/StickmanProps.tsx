import type { StickmanProp } from "./poses";
import { STICKMAN_LINE } from "./poses";

type PropsLayerProps = {
  prop: StickmanProp;
  bob: number;
  frame: number;
  fps: number;
};

export const StickmanProps: React.FC<PropsLayerProps> = ({ prop, bob, frame, fps }) => {
  const stroke = STICKMAN_LINE;
  const sw = 3.2;

  if (prop === "none") {
    return null;
  }

  if (prop === "laptop") {
    const blink = Math.floor(frame / (fps * 1.2)) % 2 === 0;
    return (
      <g transform={`translate(0, ${bob})`}>
        <rect x="118" y="248" width="120" height="72" rx="6" fill="#fff" stroke={stroke} strokeWidth={sw} />
        <rect x="126" y="256" width="104" height="52" rx="3" fill={blink ? "#e8f0fe" : "#dbeafe"} stroke={stroke} strokeWidth={1.5} />
        <line x1="118" y1="320" x2="238" y2="320" stroke={stroke} strokeWidth={sw} />
        <line x1="150" y1="320" x2="138" y2="338" stroke={stroke} strokeWidth={sw} />
        <line x1="206" y1="320" x2="218" y2="338" stroke={stroke} strokeWidth={sw} />
      </g>
    );
  }

  if (prop === "city_silhouette") {
    const slide = (frame * 0.15) % 8;
    return (
      <g opacity={0.22} transform={`translate(${-slide}, ${bob})`}>
        <rect x="250" y="170" width="36" height="90" fill="#ddd" stroke={stroke} strokeWidth={2} />
        <rect x="292" y="150" width="42" height="110" fill="#ddd" stroke={stroke} strokeWidth={2} />
        <rect x="340" y="185" width="30" height="75" fill="#ddd" stroke={stroke} strokeWidth={2} />
        <rect x="210" y="200" width="28" height="60" fill="#ddd" stroke={stroke} strokeWidth={2} />
      </g>
    );
  }

  if (prop === "signpost") {
    return (
      <g transform={`translate(0, ${bob})`}>
        <line x1="300" y1="180" x2="300" y2="330" stroke={stroke} strokeWidth={sw} />
        <rect x="248" y="188" width="92" height="28" rx="4" fill="#fff" stroke={stroke} strokeWidth={2.5} />
        <text x="294" y="208" textAnchor="middle" fontSize="14" fill={stroke}>
          城市
        </text>
        <rect x="252" y="228" width="92" height="28" rx="4" fill="#fff" stroke={stroke} strokeWidth={2.5} />
        <text x="298" y="248" textAnchor="middle" fontSize="14" fill={stroke}>
          内心
        </text>
      </g>
    );
  }

  if (prop === "tree") {
    return (
      <g transform={`translate(0, ${bob})`}>
        <line x1="310" y1="250" x2="310" y2="330" stroke={stroke} strokeWidth={sw} />
        <circle cx="310" cy="228" r="28" fill="#fff" stroke={stroke} strokeWidth={2.5} />
        <circle cx="292" cy="242" r="18" fill="#fff" stroke={stroke} strokeWidth={2} />
        <circle cx="328" cy="242" r="18" fill="#fff" stroke={stroke} strokeWidth={2} />
      </g>
    );
  }

  if (prop === "wooden_stage") {
    return (
      <g transform={`translate(0, ${bob})`}>
        <line x1="250" y1="300" x2="250" y2="340" stroke={stroke} strokeWidth={sw} />
        <line x1="290" y1="300" x2="290" y2="340" stroke={stroke} strokeWidth={sw} />
        <line x1="330" y1="300" x2="330" y2="340" stroke={stroke} strokeWidth={sw} />
        <line x1="240" y1="300" x2="340" y2="300" stroke={stroke} strokeWidth={sw} />
        <line x1="235" y1="292" x2="345" y2="292" stroke={stroke} strokeWidth={2.5} />
        <line x1="238" y1="284" x2="342" y2="284" stroke={stroke} strokeWidth={2} />
      </g>
    );
  }

  if (prop === "scroll_work") {
    return (
      <g transform={`translate(0, ${bob})`}>
        <path
          d="M 250 220 C 250 210, 290 210, 290 220 L 290 260 C 290 270, 250 270, 250 260 Z"
          fill="#fff"
          stroke={stroke}
          strokeWidth={2.5}
        />
        <text x="270" y="245" textAnchor="middle" fontSize="16" fill={stroke}>
          工作
        </text>
      </g>
    );
  }

  if (prop === "heart") {
    return (
      <g transform={`translate(0, ${bob})`}>
        <path
          d="M 300 230 C 300 210, 270 210, 270 232 C 270 252, 300 270, 300 270 C 300 270, 330 252, 330 232 C 330 210, 300 210, 300 230 Z"
          fill="#fff"
          stroke={stroke}
          strokeWidth={2.5}
        />
      </g>
    );
  }

  return null;
};
