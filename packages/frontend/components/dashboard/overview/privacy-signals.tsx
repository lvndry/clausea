"use client";

import {
  Ban,
  CheckCircle,
  Clock,
  Eye,
  HelpCircle,
  MousePointerClick,
  ShoppingCart,
  Trash2,
  Zap,
} from "lucide-react";

import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface PrivacySignalsData {
  sells_data: "yes" | "no" | "unclear";
  cross_site_tracking: "yes" | "no" | "unclear";
  account_deletion: "self_service" | "request_required" | "not_specified";
  data_retention_summary?: string | null;
  consent_model: "opt_in" | "opt_out" | "mixed" | "not_specified";
}

interface PrivacySignalsProps {
  signals: PrivacySignalsData;
}

interface SignalDisplay {
  label: string;
  value: string;
  icon: ReactNode;
  sentiment: "positive" | "negative" | "neutral";
}

function getSignalIcon(sentiment: "positive" | "negative" | "neutral") {
  if (sentiment === "positive")
    return <CheckCircle className="h-4 w-4 text-emerald-500" />;
  if (sentiment === "negative")
    return <Ban className="h-4 w-4 text-red-500" />;
  return <HelpCircle className="h-4 w-4 text-muted-foreground" />;
}

function getSentimentStyles(sentiment: "positive" | "negative" | "neutral") {
  if (sentiment === "positive")
    return "border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/50 dark:bg-emerald-950/20";
  if (sentiment === "negative")
    return "border-red-200 dark:border-red-900/50 bg-red-50/50 dark:bg-red-950/20";
  return "border-border/50 bg-muted/30";
}

function buildSignals(signals: PrivacySignalsData): SignalDisplay[] {
  const items: SignalDisplay[] = [];

  // Sells data
  const sellsMap = {
    yes: {
      value: "Yes, sells your data",
      sentiment: "negative" as const,
    },
    no: {
      value: "Does not sell your data",
      sentiment: "positive" as const,
    },
    unclear: {
      value: "Not clearly stated",
      sentiment: "neutral" as const,
    },
  };
  const sells = sellsMap[signals.sells_data];
  items.push({
    label: "Data Selling",
    value: sells.value,
    icon: <ShoppingCart className="h-4 w-4" />,
    sentiment: sells.sentiment,
  });

  // Cross-site tracking
  const trackingMap = {
    yes: {
      value: "Tracks across sites",
      sentiment: "negative" as const,
    },
    no: {
      value: "No cross-site tracking",
      sentiment: "positive" as const,
    },
    unclear: {
      value: "Not clearly stated",
      sentiment: "neutral" as const,
    },
  };
  const tracking = trackingMap[signals.cross_site_tracking];
  items.push({
    label: "Cross-Site Tracking",
    value: tracking.value,
    icon: <Eye className="h-4 w-4" />,
    sentiment: tracking.sentiment,
  });

  // Account deletion
  const deletionMap = {
    self_service: {
      value: "Self-service deletion",
      sentiment: "positive" as const,
    },
    request_required: {
      value: "Must request deletion",
      sentiment: "negative" as const,
    },
    not_specified: {
      value: "Not specified",
      sentiment: "neutral" as const,
    },
  };
  const deletion = deletionMap[signals.account_deletion];
  items.push({
    label: "Account Deletion",
    value: deletion.value,
    icon: <Trash2 className="h-4 w-4" />,
    sentiment: deletion.sentiment,
  });

  // Data retention
  if (signals.data_retention_summary) {
    items.push({
      label: "Data Retention",
      value: signals.data_retention_summary,
      icon: <Clock className="h-4 w-4" />,
      sentiment: "neutral",
    });
  }

  // Consent model
  const consentMap = {
    opt_in: {
      value: "Opt-in (your explicit consent)",
      sentiment: "positive" as const,
    },
    opt_out: {
      value: "Opt-out (pre-selected)",
      sentiment: "negative" as const,
    },
    mixed: {
      value: "Mixed approach",
      sentiment: "neutral" as const,
    },
    not_specified: {
      value: "Not specified",
      sentiment: "neutral" as const,
    },
  };
  const consent = consentMap[signals.consent_model];
  items.push({
    label: "Consent Model",
    value: consent.value,
    icon: <MousePointerClick className="h-4 w-4" />,
    sentiment: consent.sentiment,
  });

  return items;
}

export function PrivacySignals({ signals }: PrivacySignalsProps) {
  const items = buildSignals(signals);

  // Don't show if all signals are unclear/not_specified
  const hasAnySignal = items.some((item) => item.sentiment !== "neutral");
  if (!hasAnySignal) {
    return null;
  }

  return (
    <Card variant="default" className="border-border">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
            <Zap className="h-5 w-5 text-violet-600 dark:text-violet-400" />
          </div>
          <div>
            <CardTitle className="text-lg">Quick Facts</CardTitle>
            <p className="text-sm text-muted-foreground mt-0.5">
              Key privacy signals at a glance
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {items.map((item) => (
            <div
              key={item.label}
              className={cn(
                "flex items-start gap-3 p-3.5 rounded-lg border",
                getSentimentStyles(item.sentiment),
              )}
            >
              <div className="mt-0.5 shrink-0">
                {getSignalIcon(item.sentiment)}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {item.label}
                </p>
                <p className="text-sm font-medium text-foreground mt-0.5">
                  {item.value}
                </p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
