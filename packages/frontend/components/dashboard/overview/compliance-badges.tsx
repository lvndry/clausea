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
  variant: "success" | "warning" | "danger" | "outline";
} {
  if (score >= 8) return { status: "Compliant", variant: "success" };
  if (score >= 5) return { status: "Partial", variant: "warning" };
  if (score >= 1) return { status: "Non-Compliant", variant: "danger" };
  return { status: "Unknown", variant: "outline" };
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
    <Card variant="default" className="border-border">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          </div>
          <div>
            <CardTitle className="text-lg">Compliance</CardTitle>
            <p className="text-sm text-muted-foreground mt-0.5">
              Regulation compliance assessment
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {regulations.map(([regulation, score]) => {
            const info = getComplianceInfo(score);
            const label = regulationLabels[regulation] || regulation;

            return (
              <div
                key={regulation}
                className={cn(
                  "flex flex-col items-center gap-2 p-3.5 rounded-lg",
                  "border border-border/50 bg-muted/30",
                )}
              >
                <span className="text-sm font-semibold text-foreground">
                  {label}
                </span>
                <span className="text-2xl font-bold text-foreground">
                  {score}
                  <span className="text-sm font-normal text-muted-foreground">
                    /10
                  </span>
                </span>
                <Badge variant={info.variant} size="sm">
                  {info.status}
                </Badge>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
