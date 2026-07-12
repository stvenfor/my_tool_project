export type PhaseTheme = {
  background: string;
  cardBg: string;
  accent: string;
  accentSoft: string;
  orb: string;
};

export const PHASE_THEMES: Record<string, PhaseTheme> = {
  pain: {
    background: "linear-gradient(165deg, #fff8f6 0%, #ffede8 42%, #ffffff 100%)",
    cardBg: "rgba(255,255,255,0.82)",
    accent: "#e53935",
    accentSoft: "rgba(229,57,53,0.12)",
    orb: "rgba(255,107,107,0.18)",
  },
  insight: {
    background: "linear-gradient(165deg, #f5f8ff 0%, #e8f0ff 42%, #ffffff 100%)",
    cardBg: "rgba(255,255,255,0.84)",
    accent: "#2563eb",
    accentSoft: "rgba(37,99,235,0.12)",
    orb: "rgba(96,165,250,0.2)",
  },
  contrast: {
    background: "linear-gradient(165deg, #fffbeb 0%, #fef3c7 40%, #ffffff 100%)",
    cardBg: "rgba(255,255,255,0.84)",
    accent: "#d97706",
    accentSoft: "rgba(217,119,6,0.12)",
    orb: "rgba(251,191,36,0.22)",
  },
  action: {
    background: "linear-gradient(165deg, #f0fdf4 0%, #dcfce7 42%, #ffffff 100%)",
    cardBg: "rgba(255,255,255,0.84)",
    accent: "#16a34a",
    accentSoft: "rgba(22,163,74,0.12)",
    orb: "rgba(74,222,128,0.2)",
  },
  cta: {
    background: "linear-gradient(165deg, #faf5ff 0%, #f3e8ff 42%, #ffffff 100%)",
    cardBg: "rgba(255,255,255,0.84)",
    accent: "#9333ea",
    accentSoft: "rgba(147,51,234,0.12)",
    orb: "rgba(192,132,252,0.22)",
  },
};

export const DEFAULT_THEME = PHASE_THEMES.insight;

export function themeForPhase(phase?: string): PhaseTheme {
  return PHASE_THEMES[phase ?? "insight"] ?? DEFAULT_THEME;
}
