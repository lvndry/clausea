"use client";

import {
  Eye,
  Layers,
  Share2,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";

import { gradeToneStyle, gradeToneWord, scoreToGrade } from "@/lib/grade";
import { cn } from "@/lib/utils";
import type { DetailedScores } from "@/types";

interface ScoreBreakdownProps {
  detailedScores: DetailedScores;
  riskScore?: number | null;
}

const scoreConfig = {
  transparency: {
    label: "Transparency",
    description: "How clearly they explain their practices",
    icon: Eye,
  },
  data_collection_scope: {
    label: "Data Collection",
    description: "How much data they collect",
    icon: Layers,
  },
  user_control: {
    label: "User Control",
    description: "How much control you have over your data",
    icon: SlidersHorizontal,
  },
  third_party_sharing: {
    label: "Third-Party Sharing",
    description: "How widely they share your data",
    icon: Share2,
  },
} as const;

export function ScoreBreakdown({
  detailedScores,
  riskScore,
}: ScoreBreakdownProps) {
  const dimensions = Object.entries(scoreConfig).map(([key, config]) => {
    const detail = detailedScores[key as keyof DetailedScores];
    return {
      key,
      ...config,
      score: detail.score,
      justification: detail.justification,
      grade: scoreToGrade(detail.score),
    };
  });

  const riskGrade =
    riskScore != null ? scoreToGrade(riskScore, { invert: true }) : null;
  const riskStyle = riskGrade ? gradeToneStyle(riskGrade.tone) : null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SlidersHorizontal
            className="h-5 w-5 text-foreground"
            strokeWidth={1.5}
          />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Dimension Breakdown
          </h3>
        </div>
        <div className="flex items-center gap-3">
          <ShieldAlert
            className={cn(
              "h-4 w-4",
              riskStyle ? riskStyle.color : "text-muted-foreground",
            )}
            strokeWidth={1.5}
          />
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Overall Risk
          </span>
          {riskGrade && riskStyle ? (
            <div
              className={cn(
                "px-2.5 py-1 border font-display font-medium text-base leading-none",
                riskStyle.color,
                riskStyle.bg,
                riskStyle.border,
              )}
            >
              {riskGrade.letter}
            </div>
          ) : (
            <div
              className="px-2.5 py-1 border border-border font-display font-medium text-base leading-none text-muted-foreground"
              title="Insufficient dimension scores for an overall grade"
            >
              —
            </div>
          )}
        </div>
      </div>

      <div className="divide-y divide-border">
        {dimensions.map((item) => {
          const style = gradeToneStyle(item.grade.tone);

          return (
            <div key={item.key} className="p-6 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-3">
                    <span className="font-display font-medium text-xl text-foreground">
                      {item.label}
                    </span>
                    <div
                      className={cn(
                        "px-2 py-0.5 text-[8px] font-bold uppercase tracking-tighter border",
                        style.color,
                        style.bg,
                        style.border,
                      )}
                    >
                      {gradeToneWord(item.grade.tone)}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground max-w-md">
                    {item.description}
                  </p>
                </div>

                <div className="flex items-center gap-8 md:w-56">
                  <div className="flex-1 h-px bg-border relative">
                    <div
                      className={cn(
                        "absolute top-1/2 -translate-y-1/2 h-1.5 w-1.5 border transition-all duration-500",
                        style.bg,
                        style.border,
                      )}
                      style={{ left: `${item.score * 10}%` }}
                    />
                  </div>
                  <div className="flex items-baseline justify-end w-12">
                    <span
                      className={cn(
                        "text-2xl font-display font-medium leading-none",
                        style.color,
                      )}
                    >
                      {item.grade.letter}
                    </span>
                  </div>
                </div>
              </div>

              {item.justification && (
                <div className="flex items-start gap-3 border-l border-border/60 pl-4">
                  <p className="text-sm text-muted-foreground leading-relaxed italic font-serif">
                    {item.justification}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
