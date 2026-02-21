"use client";

import {
  Eye,
  Layers,
  Share2,
  SlidersHorizontal,
  Info,
} from "lucide-react";

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

function getScoreLabel(score: number): { label: string; color: string } {
  if (score >= 8) return { label: "Strong", color: "text-emerald-600 dark:text-emerald-400" };
  if (score >= 6) return { label: "Good", color: "text-green-600 dark:text-green-400" };
  if (score >= 4) return { label: "Fair", color: "text-amber-600 dark:text-amber-400" };
  if (score >= 2) return { label: "Weak", color: "text-orange-600 dark:text-orange-400" };
  return { label: "Poor", color: "text-red-600 dark:text-red-400" };
}

export function ScoreBreakdown({ detailedScores, riskScore }: ScoreBreakdownProps) {
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
    <Card variant="default" className="border-border">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
            <SlidersHorizontal className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <CardTitle className="text-lg">Score Breakdown</CardTitle>
            <p className="text-sm text-muted-foreground mt-0.5">
              How {riskScore}/10 breaks down across dimensions
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {scores.map((item) => {
          const Icon = item.icon;
          const scoreInfo = getScoreLabel(item.score);
          const isExpanded = expandedScore === item.key;

          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setExpandedScore(isExpanded ? null : item.key)}
              className={cn(
                "w-full text-left p-3.5 rounded-lg border border-border/50 bg-muted/30",
                "transition-all duration-200 hover:bg-muted/50",
              )}
            >
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2.5">
                  <div
                    className={cn(
                      "w-7 h-7 rounded-md flex items-center justify-center shrink-0",
                      item.colors.bg,
                    )}
                  >
                    <Icon className={cn("h-3.5 w-3.5", item.colors.text)} />
                  </div>
                  <div>
                    <span className="font-medium text-sm text-foreground">
                      {item.label}
                    </span>
                    <p className="text-xs text-muted-foreground">
                      {item.description}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn("text-sm font-semibold", scoreInfo.color)}>
                    {item.score}/10
                  </span>
                  <Info className={cn(
                    "h-3.5 w-3.5 text-muted-foreground/50 transition-transform",
                    isExpanded && "rotate-180"
                  )} />
                </div>
              </div>

              {/* Progress bar */}
              <div className={cn("h-1.5 rounded-full w-full", item.colors.barBg)}>
                <div
                  className={cn("h-1.5 rounded-full transition-all duration-500", item.colors.bar)}
                  style={{ width: `${item.score * 10}%` }}
                />
              </div>

              {/* Expandable justification */}
              {isExpanded && item.justification && (
                <p className="mt-3 text-sm text-muted-foreground leading-relaxed border-t border-border/50 pt-3">
                  {item.justification}
                </p>
              )}
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}
