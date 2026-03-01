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
    color: "text-[#2B7A5C]",
    bg: "bg-[#2B7A5C]/5",
    border: "border-[#2B7A5C]/20",
    label: "LOW RISK",
  },
  medium: {
    color: "text-[#B58D2D]",
    bg: "bg-[#B58D2D]/5",
    border: "border-[#B58D2D]/20",
    label: "MEDIUM",
  },
  high: {
    color: "text-[#BD452D]",
    bg: "bg-[#BD452D]/5",
    border: "border-[#BD452D]/20",
    label: "HIGH RISK",
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
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Network className="h-5 w-5 text-foreground" strokeWidth={1.5} />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Data Distribution Map
          </h3>
        </div>
        {hasStructuredData && (
          <div className="flex items-center gap-2">
            <div className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-bold bg-muted/5">
              {thirdPartyDetails?.length} Recipients
            </div>
            {highRiskCount > 0 && (
              <div className="px-3 py-1 border border-[#BD452D]/20 text-[10px] uppercase tracking-widest font-bold bg-[#BD452D]/5 text-[#BD452D]">
                {highRiskCount} High Risk
              </div>
            )}
          </div>
        )}
      </div>

      <div className="divide-y divide-border">
        {hasStructuredData ? (
          thirdPartyDetails?.map((recipient, index) => {
            const config = riskConfig[recipient.risk_level];

            return (
              <div
                key={index}
                className="grid grid-cols-1 md:grid-cols-12 group hover:bg-muted/5 transition-colors"
              >
                {/* Recipient info */}
                <div className="col-span-12 md:col-span-4 p-6 border-b md:border-b-0 md:border-r border-border bg-muted/5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <span className="text-[10px] uppercase tracking-widest text-muted-foreground block mb-2">
                        Recipient
                      </span>
                      <h4 className="font-display font-medium text-xl text-foreground">
                        {recipient.recipient}
                      </h4>
                    </div>
                    <div
                      className={cn(
                        "px-2 py-0.5 text-[8px] font-bold tracking-tighter border",
                        config.color,
                        config.bg,
                      )}
                    >
                      {config.label}
                    </div>
                  </div>
                </div>

                {/* Shared data and purpose */}
                <div className="col-span-12 md:col-span-8 p-6 space-y-4">
                  {recipient.purpose && (
                    <p className="text-sm text-foreground/80 leading-relaxed font-serif italic max-w-2xl">
                      &ldquo;{recipient.purpose}&rdquo;
                    </p>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {recipient.data_shared.map((data, dIndex) => (
                      <div
                        key={dIndex}
                        className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-medium text-muted-foreground"
                      >
                        {data}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="p-10 text-foreground leading-relaxed font-serif italic border-b border-border">
            &ldquo;{thirdPartySharing}&rdquo;
          </div>
        )}
      </div>

      {hasStructuredData && (
        <div className="p-6 border-t border-border bg-muted/5">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
            <span>Aggregated risk analysis complete</span>
            <span className="text-foreground">
              {thirdPartyDetails?.length} Vectors mapped
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
