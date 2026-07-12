import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { STICKMAN_ACCENT, STICKMAN_LINE } from "./poses";
import type { PhaseTheme } from "./theme";

type StickmanDecorationsProps = {
  extras: string[];
  theme: PhaseTheme;
};

const stroke = STICKMAN_LINE;

export const StickmanDecorations: React.FC<StickmanDecorationsProps> = ({ extras, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const drift = interpolate(Math.sin(frame / (fps * 1.4)), [-1, 1], [-10, 10]);
  const pulse = interpolate(Math.sin(frame / (fps * 0.5)), [-1, 1], [0.82, 1.12]);
  const dashOffset = (frame * 0.8) % 20;
  const clockAngle = (frame / fps) * 45;

  return (
    <g opacity={0.95}>
      <line
        x1="40"
        y1="345"
        x2="380"
        y2="345"
        stroke={theme.accent}
        strokeWidth={2.5}
        strokeDasharray="8 5"
        strokeDashoffset={-dashOffset}
        opacity={0.45}
      />

      {extras.includes("cloud") ? (
        <g transform={`translate(${drift * 0.3}, 0)`}>
          <ellipse cx="70" cy="72" rx="28" ry="16" fill="#fff" stroke={stroke} strokeWidth={2} />
          <ellipse cx="92" cy="68" rx="22" ry="14" fill="#fff" stroke={stroke} strokeWidth={2} />
        </g>
      ) : null}

      {extras.includes("sun") ? (
        <g transform={`scale(${pulse})`} style={{ transformOrigin: "340px 70px" }}>
          <circle cx="340" cy="70" r="22" fill="#ffe566" stroke={stroke} strokeWidth={2.5} />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
            <line
              key={deg}
              x1={340 + Math.cos((deg * Math.PI) / 180) * 28}
              y1={70 + Math.sin((deg * Math.PI) / 180) * 28}
              x2={340 + Math.cos((deg * Math.PI) / 180) * 38}
              y2={70 + Math.sin((deg * Math.PI) / 180) * 38}
              stroke={stroke}
              strokeWidth={2}
            />
          ))}
        </g>
      ) : null}

      {extras.includes("moon") ? (
        <path
          d="M 330 62 A 20 20 0 1 1 330 102 A 14 14 0 1 0 330 62"
          fill="#fff"
          stroke={stroke}
          strokeWidth={2}
        />
      ) : null}

      {extras.includes("stars") ? (
        <g>
          {[
            [60, 48],
            [350, 90],
            [320, 40],
          ].map(([x, y], i) => (
            <text
              key={i}
              x={x + drift * (i + 1) * 0.15}
              y={y + Math.sin(frame / (fps * (0.8 + i * 0.2))) * 4}
              fontSize="18"
              fill={theme.accent}
              opacity={0.5 + pulse * 0.3}
            >
              ✦
            </text>
          ))}
        </g>
      ) : null}

      {extras.includes("clock") ? (
        <g transform="translate(48, 200)">
          <circle cx="0" cy="0" r="22" fill="#fff" stroke={stroke} strokeWidth={2.5} />
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="-12"
            stroke={stroke}
            strokeWidth={2.5}
            transform={`rotate(${clockAngle})`}
          />
          <line
            x1="0"
            y1="0"
            x2="10"
            y2="4"
            stroke={stroke}
            strokeWidth={2.5}
            transform={`rotate(${clockAngle * 0.15})`}
          />
        </g>
      ) : null}

      {extras.includes("sweat") ? (
        <g>
          <ellipse
            cx={148}
            cy={148 + ((frame / fps) * 20) % 12}
            rx="4"
            ry="7"
            fill="#a8d4ff"
            stroke={stroke}
            strokeWidth={1.5}
            opacity={interpolate(((frame / fps) * 20) % 12, [0, 10], [1, 0.2])}
          />
          <ellipse
            cx={212}
            cy={142 + ((frame / fps) * 16 + 4) % 12}
            rx="4"
            ry="7"
            fill="#a8d4ff"
            stroke={stroke}
            strokeWidth={1.5}
            opacity={interpolate(((frame / fps) * 16 + 4) % 12, [0, 10], [1, 0.2])}
          />
        </g>
      ) : null}

      {extras.includes("stress_lines") ? (
        <g stroke={stroke} strokeWidth={2}>
          <line x1="130" y1="118" x2="118" y2="106" />
          <line x1="230" y1="118" x2="242" y2="106" />
          <line x1="136" y1="108" x2="124" y2="98" />
        </g>
      ) : null}

      {extras.includes("paper_stack") ? (
        <g transform="translate(248, 268)">
          <rect x="0" y="8" width="44" height="8" fill="#fff" stroke={stroke} strokeWidth={2} />
          <rect x="4" y="0" width="44" height="8" fill="#fff" stroke={stroke} strokeWidth={2} />
          <rect x="8" y="-8" width="44" height="8" fill="#fff" stroke={stroke} strokeWidth={2} />
        </g>
      ) : null}

      {extras.includes("coffee") ? (
        <g transform="translate(96, 286)">
          <rect x="0" y="0" width="26" height="20" rx="3" fill="#fff" stroke={stroke} strokeWidth={2} />
          <path d="M 26 6 Q 34 6 34 14 Q 34 22 26 22" fill="none" stroke={stroke} strokeWidth={2} />
          <line x1="6" y1="-4" x2="20" y2="-4" stroke={stroke} strokeWidth={2} strokeDasharray="2 3" />
        </g>
      ) : null}

      {extras.includes("thought_bubble") ? (
        <g transform={`translate(${drift}, 0)`}>
          <ellipse cx="118" cy="88" rx="38" ry="24" fill="#fff" stroke={stroke} strokeWidth={2.5} />
          <text x="118" y="94" textAnchor="middle" fontSize="14" fill={stroke}>
            ？
          </text>
          <circle cx="152" cy="112" r="5" fill="#fff" stroke={stroke} strokeWidth={2} />
          <circle cx="162" cy="122" r="3" fill="#fff" stroke={stroke} strokeWidth={2} />
        </g>
      ) : null}

      {extras.includes("question") ? (
        <text x="300" y="100" fontSize="36" fontWeight="700" fill={STICKMAN_ACCENT}>
          ?
        </text>
      ) : null}

      {extras.includes("lightbulb") ? (
        <g transform={`translate(300, 78) scale(${pulse})`}>
          <circle cx="0" cy="0" r="14" fill="#fff9c4" stroke={stroke} strokeWidth={2} />
          <rect x="-6" y="12" width="12" height="8" fill="#fff" stroke={stroke} strokeWidth={2} />
        </g>
      ) : null}

      {extras.includes("arrow_left") ? (
        <g transform="translate(52, 220)">
          <line x1="20" y1="0" x2="0" y2="0" stroke={stroke} strokeWidth={3} markerEnd="url(#arrow)" />
          <polygon points="0,0 -10,-6 -10,6" fill={stroke} />
        </g>
      ) : null}

      {extras.includes("arrow_right") ? (
        <g transform="translate(340, 220)">
          <line x1="0" y1="0" x2="20" y2="0" stroke={stroke} strokeWidth={3} />
          <polygon points="20,0 10,-6 10,6" fill={stroke} />
        </g>
      ) : null}

      {extras.includes("bird") ? (
        <path
          d={`M ${120 + drift} 110 Q ${130 + drift} 100 ${140 + drift} 110`}
          fill="none"
          stroke={stroke}
          strokeWidth={2.5}
        />
      ) : null}

      {extras.includes("flower") ? (
        <g transform="translate(72, 300)">
          <line x1="0" y1="0" x2="0" y2="24" stroke={stroke} strokeWidth={2} />
          <circle cx="0" cy="-4" r="8" fill="#ffb3c1" stroke={stroke} strokeWidth={1.5} />
        </g>
      ) : null}

      {extras.includes("path") ? (
        <path
          d="M 60 345 Q 140 320 220 345 T 380 345"
          fill="none"
          stroke={stroke}
          strokeWidth={2}
          strokeDasharray="5 5"
        />
      ) : null}

      {extras.includes("scale") ? (
        <g transform="translate(210, 118)">
          <line x1="0" y1="0" x2="0" y2="30" stroke={stroke} strokeWidth={2.5} />
          <line x1="-24" y1="0" x2="24" y2="0" stroke={stroke} strokeWidth={2.5} />
          <line x1="-24" y1="0" x2="-34" y2="16" stroke={stroke} strokeWidth={2} />
          <line x1="24" y1="0" x2="34" y2="16" stroke={stroke} strokeWidth={2} />
        </g>
      ) : null}

      {extras.includes("exclaim") ? (
        <text x="88" y="120" fontSize="32" fontWeight="800" fill="#e53935">
          !
        </text>
      ) : null}

      {extras.includes("crowd_dots") ? (
        <g>
          {[
            [60, 260],
            [80, 272],
            [100, 258],
          ].map(([x, y], i) => (
            <g key={i}>
              <circle cx={x} cy={y - 14} r="8" fill="#fff" stroke={stroke} strokeWidth={2} />
              <line x1={x} y1={y - 6} x2={x} y2={y + 8} stroke={stroke} strokeWidth={2} />
            </g>
          ))}
        </g>
      ) : null}

      {extras.includes("spotlight") ? (
        <polygon points="250,40 310,40 340,345 220,345" fill="rgba(255,236,150,0.12)" stroke="none" />
      ) : null}

      {extras.includes("flag") ? (
        <g transform="translate(48, 170)">
          <line x1="0" y1="0" x2="0" y2="50" stroke={stroke} strokeWidth={2.5} />
          <polygon points="0,0 28,8 0,16" fill="#ff6b6b" stroke={stroke} strokeWidth={1.5} />
        </g>
      ) : null}

      {extras.includes("spark") || extras.includes("crown_sparkle") ? (
        <g>
          {[
            [100, 90],
            [310, 130],
            [260, 60],
          ].map(([x, y], i) => (
            <text
              key={i}
              x={x + drift * (i + 1) * 0.2}
              y={y}
              fontSize="16"
              fill="#f4c430"
              opacity={pulse}
            >
              ✧
            </text>
          ))}
        </g>
      ) : null}

      {extras.includes("star") ? (
        <text x="320" y="180" fontSize="28" fill="#f4c430">
          ★
        </text>
      ) : null}

      {extras.includes("coin") ? (
        <circle cx="96" cy="230" r="12" fill="#ffe566" stroke={stroke} strokeWidth={2} />
      ) : null}

      {extras.includes("heart") ? (
        <text x="330" y="260" fontSize="24" fill="#ff6b8a">
          ♥
        </text>
      ) : null}

      {extras.includes("thumb") ? (
        <g transform="translate(300, 180)">
          <rect x="0" y="0" width="16" height="24" rx="4" fill="#fff" stroke={stroke} strokeWidth={2} />
          <rect x="-8" y="10" width="10" height="8" rx="2" fill="#fff" stroke={stroke} strokeWidth={2} />
        </g>
      ) : null}
    </g>
  );
};
