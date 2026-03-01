"use client";

import { Eye, Info, Layers, Share2, SlidersHorizontal } from "lucide-react";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface DetailedScore {
  score: number;
  justification: string;
}

interface DetailedScores {
  transparency: DetailedScore;
  data_collection_scope: DetailedScore;
  user_control: DetailedScore;
  third_party_sharing: DetailedScore;
}

interface ScoreBreakdownProps {
  detailedScores: DetailedScores;
  riskScore: number;
}

const scoreConfig = {
  transparency: {
    label: "Transparency",
    description: "How clearly they explain their practices",
    icon: Eye,
    color: "blue",
  },
  data_collection_scope: {
    label: "Data Collection",
    description: "How much data they collect",
    icon: Layers,
    color: "purple",
  },
  user_control: {
    label: "User Control",
    description: "How much control you have over your data",
    icon: SlidersHorizontal,
    color: "emerald",
  },
  third_party_sharing: {
    label: "Third-Party Sharing",
    description: "How widely they share your data",
    icon: Share2,
    color: "orange",
  },
} as const;

const colorClasses = {
  blue: {
    bg: "bg-blue-100 dark:bg-blue-900/30",
    text: "text-blue-600 dark:text-blue-400",
    bar: "bg-blue-500",
    barBg: "bg-blue-100 dark:bg-blue-900/30",
  },
  purple: {
    bg: "bg-purple-100 dark:bg-purple-900/30",
    text: "text-purple-600 dark:text-purple-400",
    bar: "bg-purple-500",
    barBg: "bg-purple-100 dark:bg-purple-900/30",
  },
  emerald: {
    bg: "bg-emerald-100 dark:bg-emerald-900/30",
    text: "text-emerald-600 dark:text-emerald-400",
    bar: "bg-emerald-500",
    barBg: "bg-emerald-100 dark:bg-emerald-900/30",
  },
  orange: {
    bg: "bg-orange-100 dark:bg-orange-900/30",
    text: "text-orange-600 dark:text-orange-400",
    bar: "bg-orange-500",
    barBg: "bg-orange-100 dark:bg-orange-900/30",
  },
} as const;

function getScoreLabel(score: number): {
  label: string;
  color: string;
  bg: string;
} {
  if (score >= 8)
    return { label: "STRONG", color: "text-[#2B7A5C]", bg: "bg-[#2B7A5C]/5" };
  if (score >= 6)
    return { label: "GOOD", color: "text-[#2B7A5C]", bg: "bg-[#2B7A5C]/5" };
  if (score >= 4)
    return { label: "FAIR", color: "text-[#B58D2D]", bg: "bg-[#B58D2D]/5" };
  if (score >= 2)
    return { label: "WEAK", color: "text-[#BD452D]", bg: "bg-[#BD452D]/5" };
  return { label: "POOR", color: "text-[#BD452D]", bg: "bg-[#BD452D]/5" };
}

export function ScoreBreakdown({
  detailedScores,
  riskScore,
}: ScoreBreakdownProps) {
  const [expandedScore, setExpandedScore] = useState<string | null>(null);

  const scores = Object.entries(scoreConfig).map(([key, config]) => {
    const score = detailedScores[key as keyof DetailedScores];
    return {
      key,
      ...config,
      score: score.score,
      justification: score.justification,
      colors: colorClasses[config.color],
    };
  });

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
      </div>

      <div className="divide-y divide-border">
        {scores.map((item) => {
          const scoreInfo = getScoreLabel(item.score);
          const isExpanded = expandedScore === item.key;

          return (
            <div key={item.key} className="group">
              <button
                type="button"
                onClick={() => setExpandedScore(isExpanded ? null : item.key)}
                className="w-full text-left p-6 flex flex-col md:flex-row md:items-center justify-between gap-6 hover:bg-muted/5 transition-colors"
              >
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-3">
                    <span className="font-display font-medium text-xl text-foreground">
                      {item.label}
                    </span>
                    <div
                      className={cn(
                        "px-2 py-0.5 text-[8px] font-bold tracking-tighter border",
                        scoreInfo.color,
                        scoreInfo.bg,
                      )}
                    >
                      {scoreInfo.label}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground max-w-md">
                    {item.description}
                  </p>
                </div>

                <div className="flex items-center gap-8 md:w-64">
                  {/* Minimal progress bar */}
                  <div className="flex-1 h-px bg-border relative">
                    <div
                      className={cn(
                        "absolute top-1/2 -translate-y-1/2 h-1.5 w-1.5 border border-border transition-all duration-500",
                        scoreInfo.bg,
                      )}
                      style={{ left: `${item.score * 10}%` }}
                    />
                  </div>
                  <div className="flex items-baseline gap-1 w-12 justify-end">
                    <span className="text-lg font-display font-medium text-foreground">
                      {item.score}
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
                      /10
                    </span>
                  </div>
                  <Info
                    className={cn(
                      "h-3.5 w-3.5 text-muted-foreground/30 transition-transform hidden md:block",
                      isExpanded && "rotate-180 text-foreground",
                    )}
                  />
                </div>
              </button>

              {isExpanded && item.justification && (
                <div className="px-6 pb-6 pt-0">
                  <div className="p-6 bg-muted/5 border border-border/50 text-sm text-muted-foreground leading-relaxed italic font-serif">
                    &ldquo;{item.justification}&rdquo;
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
