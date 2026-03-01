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
    return <CheckCircle className="h-4 w-4 text-[#2B7A5C]" strokeWidth={1.5} />;
  if (sentiment === "negative")
    return <Ban className="h-4 w-4 text-[#BD452D]" strokeWidth={1.5} />;
  return (
    <HelpCircle className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
  );
}

function getSentimentStyles(sentiment: "positive" | "negative" | "neutral") {
  if (sentiment === "positive")
    return "border-[#2B7A5C]/20 bg-[#2B7A5C]/5 text-[#2B7A5C]";
  if (sentiment === "negative")
    return "border-[#BD452D]/20 bg-[#BD452D]/5 text-[#BD452D]";
  return "border-border bg-muted/5 text-muted-foreground";
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
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-foreground" strokeWidth={1.5} />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Privacy Signals
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3">
        {items.map((item, idx) => (
          <div
            key={item.label}
            className={cn(
              "p-6 flex flex-col gap-4 border-b border-border transition-colors group",
              idx % 3 !== 2 ? "md:border-r border-border" : "",
            )}
          >
            <div className="flex justify-between items-start">
              <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground group-hover:text-foreground transition-colors">
                {item.label}
              </span>
              <div
                className={cn(
                  "px-2 py-0.5 text-[8px] font-bold tracking-tighter border",
                  getSentimentStyles(item.sentiment),
                )}
              >
                {item.sentiment === "positive"
                  ? "SAFE"
                  : item.sentiment === "negative"
                    ? "RISK"
                    : "NEUTRAL"}
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="mt-1 shrink-0">
                {getSignalIcon(item.sentiment)}
              </div>
              <p className="text-sm font-medium text-foreground leading-tight">
                {item.value}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
