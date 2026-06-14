export type GradeTone = "good" | "ok" | "warn" | "bad";

export interface Grade {
  letter: string;
  tone: GradeTone;
}

export interface GradeStyle {
  color: string;
  bg: string;
  border: string;
}

const GRADE_TONE_STYLES: Record<GradeTone, GradeStyle> = {
  good: {
    color: "text-[#2B7A5C]",
    bg: "bg-[#2B7A5C]/5",
    border: "border-[#2B7A5C]/20",
  },
  ok: {
    color: "text-[#B58D2D]",
    bg: "bg-[#B58D2D]/5",
    border: "border-[#B58D2D]/20",
  },
  warn: {
    color: "text-[#B58D2D]",
    bg: "bg-[#B58D2D]/5",
    border: "border-[#B58D2D]/20",
  },
  bad: {
    color: "text-[#BD452D]",
    bg: "bg-[#BD452D]/5",
    border: "border-[#BD452D]/20",
  },
};

interface GradeBand {
  min: number;
  letter: string;
  tone: GradeTone;
}

// Bands map a 0-10 "higher = better" score to a 13-step letter scale.
// good: A+ A A-  |  ok: B+ B B-  |  warn: C+ C C-  |  bad: D+ D D- E
const GRADE_BANDS: GradeBand[] = [
  { min: 9.5, letter: "A+", tone: "good" },
  { min: 8.5, letter: "A", tone: "good" },
  { min: 8.0, letter: "A-", tone: "good" },
  { min: 7.5, letter: "B+", tone: "ok" },
  { min: 6.5, letter: "B", tone: "ok" },
  { min: 6.0, letter: "B-", tone: "ok" },
  { min: 5.5, letter: "C+", tone: "warn" },
  { min: 4.5, letter: "C", tone: "warn" },
  { min: 4.0, letter: "C-", tone: "warn" },
  { min: 3.5, letter: "D+", tone: "bad" },
  { min: 2.5, letter: "D", tone: "bad" },
  { min: 1.0, letter: "D-", tone: "bad" },
  { min: -Infinity, letter: "E", tone: "bad" },
];

export function scoreToGrade(
  score: number,
  opts?: { invert?: boolean },
): Grade {
  const clamped = Math.max(0, Math.min(10, score));
  // riskScore is "higher = worse"; inverting maps it onto the "higher = better" bands.
  const effective = opts?.invert ? 10 - clamped : clamped;
  const band = GRADE_BANDS.find((entry) => effective >= entry.min) ?? GRADE_BANDS[GRADE_BANDS.length - 1];
  return { letter: band.letter, tone: band.tone };
}

export function gradeToneStyle(tone: GradeTone): GradeStyle {
  return GRADE_TONE_STYLES[tone];
}

const TONE_WORDS: Record<GradeTone, string> = {
  good: "Strong",
  ok: "Good",
  warn: "Fair",
  bad: "Weak",
};

export function gradeToneWord(tone: GradeTone): string {
  return TONE_WORDS[tone];
}
