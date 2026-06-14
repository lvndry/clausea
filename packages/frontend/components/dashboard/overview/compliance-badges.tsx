"use client";

import { Check, ShieldCheck, X } from "lucide-react";

import { gradeToneStyle, scoreToGrade } from "@/lib/grade";
import { cn } from "@/lib/utils";

export type ComplianceStatus =
  | "Compliant"
  | "Partially Compliant"
  | "Non-Compliant"
  | "Unknown";

export interface ComplianceBreakdown {
  score: number;
  status: ComplianceStatus;
  strengths: string[];
  gaps: string[];
}

interface ComplianceBadgesProps {
  compliance?: Record<string, ComplianceBreakdown> | null;
  complianceStatus?: Record<string, number> | null;
}

const regulationLabels: Record<string, string> = {
  GDPR: "GDPR",
  CCPA: "CCPA",
  PIPEDA: "PIPEDA",
  LGPD: "LGPD",
};

const statusStyles: Record<ComplianceStatus, string> = {
  Compliant: "border-risk-low/20 bg-risk-low/5 text-risk-low",
  "Partially Compliant": "border-risk-medium/20 bg-risk-medium/5 text-risk-medium",
  "Non-Compliant": "border-risk-high/20 bg-risk-high/5 text-risk-high",
  Unknown: "border-border bg-muted/5 text-muted-foreground",
};

function statusFromScore(score: number): ComplianceStatus {
  if (score >= 8) return "Compliant";
  if (score >= 5) return "Partially Compliant";
  if (score >= 1) return "Non-Compliant";
  return "Unknown";
}

function ChromeHeader() {
  return (
    <div className="p-6 border-b border-border flex items-center gap-3">
      <ShieldCheck className="h-5 w-5 text-foreground" strokeWidth={1.5} />
      <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
        Compliance Assessment
      </h3>
    </div>
  );
}

export function ComplianceBadges({
  compliance,
  complianceStatus,
}: ComplianceBadgesProps) {
  const entries: Array<[string, ComplianceBreakdown]> = compliance
    ? Object.entries(compliance)
    : complianceStatus
      ? Object.entries(complianceStatus)
          .filter(([, score]) => score !== null && score !== undefined)
          .map(([regulation, score]) => [
            regulation,
            {
              score,
              status: statusFromScore(score),
              strengths: [],
              gaps: [],
            },
          ])
      : [];

  if (entries.length === 0) {
    return (
      <div className="border border-border bg-background">
        <ChromeHeader />
        <div className="p-6">
          <p className="text-sm text-muted-foreground italic font-serif">
            No regulatory compliance assessment is available for this product
            yet.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-border bg-background">
      <ChromeHeader />

      <div className="divide-y divide-border">
        {entries.map(([regulation, breakdown]) => {
          const grade = scoreToGrade(breakdown.score);
          const style = gradeToneStyle(grade.tone);
          const label = regulationLabels[regulation] ?? regulation;

          return (
            <div
              key={regulation}
              className="p-6 flex flex-col md:flex-row md:items-start gap-6"
            >
              <div className="flex items-center gap-4 md:w-56 shrink-0">
                <span
                  className={cn(
                    "font-display font-medium text-3xl leading-none",
                    style.color,
                  )}
                >
                  {grade.letter}
                </span>
                <div className="space-y-1.5">
                  <span className="font-display font-medium text-lg text-foreground block">
                    {label}
                  </span>
                  <div
                    className={cn(
                      "px-2 py-0.5 text-[8px] font-bold uppercase tracking-tighter border w-fit",
                      statusStyles[breakdown.status],
                    )}
                  >
                    {breakdown.status}
                  </div>
                </div>
              </div>

              <div className="flex-1 space-y-3">
                {breakdown.strengths.length === 0 &&
                  breakdown.gaps.length === 0 && (
                    <p className="text-sm text-muted-foreground italic font-serif">
                      No detailed assessment notes available.
                    </p>
                  )}
                {breakdown.strengths.map((strength) => (
                  <div key={strength} className="flex items-start gap-3">
                    <Check
                      className="h-4 w-4 text-risk-low mt-0.5 shrink-0"
                      strokeWidth={1.5}
                    />
                    <p className="text-sm text-foreground/80 leading-relaxed">
                      {strength}
                    </p>
                  </div>
                ))}
                {breakdown.gaps.map((gap) => (
                  <div key={gap} className="flex items-start gap-3">
                    <X
                      className="h-4 w-4 text-risk-high mt-0.5 shrink-0"
                      strokeWidth={1.5}
                    />
                    <p className="text-sm text-foreground/80 leading-relaxed">
                      {gap}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
