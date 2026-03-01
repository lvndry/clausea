"use client";

import { ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ComplianceBadgesProps {
  complianceStatus: Record<string, number>;
}

function getComplianceInfo(score: number): {
  status: string;
  color: string;
  bg: string;
} {
  if (score >= 8)
    return {
      status: "COMPLIANT",
      color: "text-[#2B7A5C]",
      bg: "bg-[#2B7A5C]/5",
    };
  if (score >= 5)
    return { status: "PARTIAL", color: "text-[#B58D2D]", bg: "bg-[#B58D2D]/5" };
  if (score >= 1)
    return {
      status: "NON-COMPLIANT",
      color: "text-[#BD452D]",
      bg: "bg-[#BD452D]/5",
    };
  return {
    status: "UNKNOWN",
    color: "text-muted-foreground",
    bg: "bg-muted/5",
  };
}

const regulationLabels: Record<string, string> = {
  GDPR: "GDPR",
  CCPA: "CCPA",
  PIPEDA: "PIPEDA",
  LGPD: "LGPD",
};

export function ComplianceBadges({ complianceStatus }: ComplianceBadgesProps) {
  const regulations = Object.entries(complianceStatus).filter(
    ([, score]) => score !== null && score !== undefined,
  );

  if (regulations.length === 0) {
    return null;
  }

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-foreground" strokeWidth={1.5} />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Compliance Assessment
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4">
        {regulations.map(([regulation, score], idx) => {
          const info = getComplianceInfo(score);
          const label = regulationLabels[regulation] || regulation;

          return (
            <div
              key={regulation}
              className={cn(
                "p-6 flex flex-col gap-4 bg-background",
                idx % 4 !== 3 ? "md:border-r border-border" : "",
                idx < 4 ? "md:border-b-0" : "border-t",
                "border-b border-r sm:border-r", // Basic mobile grid
              )}
            >
              <div className="flex justify-between items-start">
                <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
                  {label}
                </span>
                <div
                  className={cn(
                    "px-2 py-0.5 text-[8px] font-bold tracking-tighter border border-border",
                    info.color,
                    info.bg,
                  )}
                >
                  {info.status}
                </div>
              </div>

              <div className="flex items-baseline gap-1">
                <span className="text-3xl font-display font-medium text-foreground leading-none">
                  {score}
                </span>
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">
                  /10
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
