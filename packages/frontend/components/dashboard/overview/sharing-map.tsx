"use client";

import {
  AlertTriangle,
  Building2,
  CheckCircle,
  Network,
  Shield,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ThirdPartyRecipient {
  recipient: string;
  data_shared: string[];
  purpose?: string | null;
  risk_level: "low" | "medium" | "high";
}

interface SharingMapProps {
  thirdPartyDetails?: ThirdPartyRecipient[] | null;
  thirdPartySharing?: string | null;
}

const riskConfig = {
  low: {
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-950/20",
    border: "border-green-200 dark:border-green-800",
    iconBg: "bg-green-100 dark:bg-green-900/30",
    icon: Shield,
    label: "Low",
    badgeVariant: "success" as const,
  },
  medium: {
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-50 dark:bg-amber-950/20",
    border: "border-amber-200 dark:border-amber-800",
    iconBg: "bg-amber-100 dark:bg-amber-900/30",
    icon: CheckCircle,
    label: "Medium",
    badgeVariant: "warning" as const,
  },
  high: {
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-950/20",
    border: "border-red-200 dark:border-red-800",
    iconBg: "bg-red-100 dark:bg-red-900/30",
    icon: AlertTriangle,
    label: "High Risk",
    badgeVariant: "danger" as const,
  },
};

export function SharingMap({
  thirdPartyDetails,
  thirdPartySharing,
}: SharingMapProps) {
  const hasStructuredData = thirdPartyDetails && thirdPartyDetails.length > 0;
  const hasFallback = thirdPartySharing && thirdPartySharing.length > 0;

  if (!hasStructuredData && !hasFallback) {
    return null;
  }

  const highRiskCount =
    thirdPartyDetails?.filter((t) => t.risk_level === "high").length || 0;
  const mediumRiskCount =
    thirdPartyDetails?.filter((t) => t.risk_level === "medium").length || 0;

  return (
    <Card variant="default" className="border-border">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
              <Network className="h-5 w-5 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <CardTitle className="text-lg">Who Has Your Data</CardTitle>
              <p className="text-sm text-muted-foreground mt-0.5">
                Third parties that receive your data
              </p>
            </div>
          </div>

          {hasStructuredData && (
            <div className="flex items-center gap-2">
              {highRiskCount > 0 && (
                <Badge variant="danger" size="sm" className="gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {highRiskCount}
                </Badge>
              )}
              <Badge variant="outline" size="sm" className="gap-1">
                <Building2 className="h-3 w-3" />
                {thirdPartyDetails.length}
              </Badge>
            </div>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {hasStructuredData ? (
          <div className="space-y-2.5">
            {thirdPartyDetails.map((recipient, index) => {
              const config = riskConfig[recipient.risk_level];
              const Icon = config.icon;

              return (
                <div
                  key={index}
                  className={cn(
                    "p-4 rounded-lg border",
                    config.bg,
                    config.border,
                  )}
                >
                  <div className="flex flex-col sm:flex-row sm:items-start gap-3">
                    {/* Recipient info */}
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      <div
                        className={cn(
                          "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
                          config.iconBg,
                        )}
                      >
                        <Icon className={cn("h-4.5 w-4.5", config.color)} />
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <h4 className="font-semibold text-sm text-foreground truncate">
                            {recipient.recipient}
                          </h4>
                          <Badge
                            variant={config.badgeVariant}
                            size="sm"
                            className="shrink-0"
                          >
                            {config.label}
                          </Badge>
                        </div>

                        {recipient.purpose && (
                          <p className="text-sm text-muted-foreground mb-2 line-clamp-2">
                            {recipient.purpose}
                          </p>
                        )}

                        {/* Shared data badges */}
                        <div className="flex flex-wrap gap-1.5">
                          {recipient.data_shared.map((data, dIndex) => (
                            <Badge
                              key={dIndex}
                              variant="outline"
                              size="sm"
                              className="bg-background/50"
                            >
                              {data}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-foreground/80 leading-relaxed text-sm">
            {thirdPartySharing}
          </p>
        )}

        {/* Summary footer */}
        {hasStructuredData && (
          <div className="pt-3 border-t border-border/50">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <span className="text-muted-foreground">
                Data shared with{" "}
                <span className="font-medium text-foreground">
                  {thirdPartyDetails.length} third parties
                </span>
              </span>

              <div className="flex items-center gap-3 ml-auto">
                {highRiskCount > 0 && (
                  <span
                    className={cn(
                      "flex items-center gap-1.5 font-medium",
                      riskConfig.high.color,
                    )}
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {highRiskCount} high-risk
                  </span>
                )}
                {mediumRiskCount > 0 && (
                  <span
                    className={cn(
                      "flex items-center gap-1.5 font-medium",
                      riskConfig.medium.color,
                    )}
                  >
                    <CheckCircle className="h-3.5 w-3.5" />
                    {mediumRiskCount} medium
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
