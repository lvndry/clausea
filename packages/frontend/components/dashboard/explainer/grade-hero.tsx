"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Shield,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import MarkdownRenderer from "@/components/markdown/markdown-renderer";
import { cn } from "@/lib/utils";

import {
  type ConsumerExplainer,
  type ConsumerGrade,
  normalizeConfidence,
  normalizeGrade,
} from "./types";

interface GradeHeroProps {
  explainer: ConsumerExplainer;
  tlDr: string | null;
}

interface GradeStyle {
  word: string;
  worry: string;
  color: string;
  bg: string;
  border: string;
  rule: string;
  icon: LucideIcon;
}

const gradeStyles: Record<ConsumerGrade, GradeStyle> = {
  A: {
    word: "Reassuring",
    worry: "Not much to worry about here.",
    color: "text-[#2B7A5C]",
    bg: "bg-[#2B7A5C]/5",
    border: "border-[#2B7A5C]/20",
    rule: "bg-[#2B7A5C]",
    icon: ShieldCheck,
  },
  B: {
    word: "Mostly fair",
    worry: "A few things to keep an eye on.",
    color: "text-[#2B7A5C]",
    bg: "bg-[#2B7A5C]/5",
    border: "border-[#2B7A5C]/20",
    rule: "bg-[#2B7A5C]",
    icon: CheckCircle2,
  },
  C: {
    word: "Mixed",
    worry: "Worth reading before you agree.",
    color: "text-[#B58D2D]",
    bg: "bg-[#B58D2D]/5",
    border: "border-[#B58D2D]/20",
    rule: "bg-[#B58D2D]",
    icon: Shield,
  },
  D: {
    word: "Concerning",
    worry: "There are real reasons to be cautious.",
    color: "text-[#BD452D]",
    bg: "bg-[#BD452D]/5",
    border: "border-[#BD452D]/20",
    rule: "bg-[#BD452D]",
    icon: ShieldAlert,
  },
  E: {
    word: "Alarming",
    worry: "You should think hard before agreeing to this.",
    color: "text-[#BD452D]",
    bg: "bg-[#BD452D]/5",
    border: "border-[#BD452D]/20",
    rule: "bg-[#BD452D]",
    icon: AlertTriangle,
  },
};

const unknownStyle: GradeStyle = {
  word: "Not yet graded",
  worry: "We could not assign a grade with confidence.",
  color: "text-muted-foreground",
  bg: "bg-muted/5",
  border: "border-border",
  rule: "bg-border",
  icon: Shield,
};

const confidenceLabel: Record<"high" | "medium" | "low", string> = {
  high: "High confidence",
  medium: "Moderate confidence",
  low: "Low confidence — read the source",
};

export function GradeHero({ explainer, tlDr }: GradeHeroProps) {
  const grade = normalizeGrade(explainer.grade);
  const style = grade ? gradeStyles[grade] : unknownStyle;
  const Icon = style.icon;
  const confidence = normalizeConfidence(explainer.confidence);
  const criticalCount = explainer.critical_findings_count ?? 0;
  const hasCritical = criticalCount > 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-12 border border-border bg-background">
      {/* Grade panel */}
      <div
        className={cn(
          "col-span-12 md:col-span-4 p-8 border-b md:border-b-0 md:border-r border-border flex flex-col justify-between",
          style.bg,
        )}
      >
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground block mb-6">
            Grade
          </span>
          <div className="flex flex-col gap-2">
            <span
              className={cn(
                "font-display font-medium leading-[0.8] tracking-tight text-[7rem] md:text-[8rem]",
                style.color,
              )}
            >
              {grade ?? "—"}
            </span>
            <div className="flex flex-col gap-1">
              <span
                className={cn(
                  "font-display font-medium text-2xl leading-tight",
                  style.color,
                )}
              >
                {style.word}
              </span>
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Grade {grade ?? "pending"} of A–E
              </span>
            </div>
          </div>
        </div>

        <div className="mt-10 space-y-4">
          <div
            className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 border text-[10px] uppercase tracking-widest font-bold",
              style.color,
              style.border,
              style.bg,
            )}
          >
            <Icon className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
            {style.word}
          </div>
          <p className={cn("text-sm leading-relaxed", style.color)}>
            {style.worry}
          </p>
          {confidence && (
            <p className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
              {confidenceLabel[confidence]}
            </p>
          )}
        </div>
      </div>

      {/* Narrative panel */}
      <div className="col-span-12 md:col-span-8 flex flex-col">
        <div className="p-8 md:p-10 flex-1">
          <span className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground block mb-6">
            The short version
          </span>
          {explainer.headline && (
            <h2 className="font-display font-medium text-3xl md:text-4xl leading-[1.1] tracking-tight text-foreground mb-6 max-w-2xl">
              {explainer.headline}
            </h2>
          )}
          {tlDr && (
            <div className="text-lg text-foreground/90 leading-relaxed max-w-2xl prose prose-slate dark:prose-invert">
              <MarkdownRenderer>{tlDr}</MarkdownRenderer>
            </div>
          )}
          {explainer.grade_reason && (
            <p className="mt-6 text-sm text-muted-foreground leading-relaxed max-w-2xl border-l-2 border-border pl-4">
              {explainer.grade_reason}
            </p>
          )}
        </div>

        {/* Critical-finding banner — must read as serious */}
        {hasCritical && (
          <div className="p-8 md:p-10 border-t border-[#BD452D]/20 bg-[#BD452D]/5">
            <div className="flex items-start gap-4">
              <AlertTriangle
                className="h-5 w-5 shrink-0 text-[#BD452D] mt-0.5"
                strokeWidth={2}
                aria-hidden="true"
              />
              <div>
                <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#BD452D] mb-2">
                  {criticalCount} critical{" "}
                  {criticalCount === 1 ? "finding" : "findings"}
                </p>
                <p className="text-sm text-foreground leading-relaxed max-w-2xl">
                  This document contains{" "}
                  {criticalCount === 1 ? "a term" : "terms"} that could
                  seriously affect you. Read the watch-outs below before you
                  agree.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
