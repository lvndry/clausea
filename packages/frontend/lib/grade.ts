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

export function letterGradeToTone(letter: string): GradeTone {
  switch (letter.toUpperCase().charAt(0)) {
    case "A":
      return "good";
    case "B":
      return "ok";
    case "C":
      return "warn";
    default:
      return "bad";
  }
}

export function parseLetterGrade(letter: string): Grade {
  const normalized = letter.trim().toUpperCase().charAt(0);
  if (!["A", "B", "C", "D", "E"].includes(normalized)) {
    return { letter: "—", tone: "warn" };
  }
  return { letter: normalized, tone: letterGradeToTone(normalized) };
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
