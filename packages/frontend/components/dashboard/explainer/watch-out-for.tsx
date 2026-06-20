"use client";

import { AlertTriangle, ChevronDown, ExternalLink, Quote } from "lucide-react";

import { useState } from "react";

import { cn } from "@/lib/utils";

import {
  type ConsumerCase,
  type ConsumerSeverity,
  hasCitation,
  normalizeSeverity,
} from "./types";

interface WatchOutForProps {
  cases: ConsumerCase[];
}

const severityStyle: Record<
  ConsumerSeverity,
  { label: string; color: string; bg: string; border: string; rule: string }
> = {
  critical: {
    label: "Critical",
    color: "text-risk-high",
    bg: "bg-risk-high/5",
    border: "border-risk-high/20",
    rule: "bg-risk-high",
  },
  high: {
    label: "High",
    color: "text-risk-high",
    bg: "bg-risk-high/5",
    border: "border-risk-high/20",
    rule: "bg-risk-high",
  },
  medium: {
    label: "Medium",
    color: "text-risk-medium",
    bg: "bg-risk-medium/5",
    border: "border-risk-medium/20",
    rule: "bg-risk-medium",
  },
  low: {
    label: "Low",
    color: "text-risk-low",
    bg: "bg-risk-low/5",
    border: "border-risk-low/20",
    rule: "bg-risk-low",
  },
};

function humanizeSource(value: string | null | undefined): string | null {
  const cleaned = value?.trim();
  if (!cleaned) return null;
  return cleaned.replace(/_/g, " ");
}

function WatchOutCard({ item, index }: { item: ConsumerCase; index: number }) {
  const [showQuote, setShowQuote] = useState(false);
  const severity = normalizeSeverity(item.severity);
  const style = severityStyle[severity];
  const citationVisible = hasCitation(item.quote_status) && Boolean(item.quote);
  const quoteId = `watch-out-quote-${index}`;
  const citation = item.citation;
  const sourceLabel =
    humanizeSource(citation?.document_title) ??
    humanizeSource(citation?.document_type) ??
    "the source document";
  const displayedQuote = citation?.quote || item.quote;

  return (
    <div className="group grid grid-cols-1 md:grid-cols-12">
      {/* Severity rail */}
      <div className="col-span-12 md:col-span-3 p-6 border-b md:border-b-0 md:border-r border-border bg-muted/5 flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <span className={cn("h-8 w-1", style.rule)} aria-hidden="true" />
          <div
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-1 border text-[10px] uppercase tracking-widest font-bold",
              style.color,
              style.bg,
              style.border,
            )}
          >
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            {style.label}
          </div>
        </div>
        {item.title && (
          <h4 className="font-display font-medium text-lg leading-snug text-foreground">
            {item.title}
          </h4>
        )}
        {item.classification && (
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            {item.classification.replace(/_/g, " ")}
          </span>
        )}
      </div>

      {/* The consequence — the visual focus */}
      <div className="col-span-12 md:col-span-9 p-6 md:p-8 space-y-5">
        <div>
          <span className="text-[10px] uppercase tracking-[0.2em] font-medium text-muted-foreground block mb-3">
            What this means for you
          </span>
          <p className="text-lg md:text-xl text-foreground leading-relaxed max-w-2xl">
            {item.means_for_you ??
              "This term may affect you, but the consequence could not be summarized."}
          </p>
        </div>

        {citationVisible && (
          <div>
            <button
              type="button"
              onClick={() => setShowQuote((open) => !open)}
              aria-expanded={showQuote}
              aria-controls={quoteId}
              className="inline-flex items-center gap-2 text-[10px] uppercase tracking-widest font-bold text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <Quote className="h-3 w-3" aria-hidden="true" />
              {showQuote ? "Hide the wording" : "Show me where it says that"}
              <ChevronDown
                className={cn(
                  "h-3 w-3 transition-transform",
                  showQuote && "rotate-180",
                )}
                aria-hidden="true"
              />
            </button>
            {showQuote && (
              <div
                id={quoteId}
                className="mt-4 border-l-2 border-border bg-muted/5 p-5"
              >
                <p className="text-sm text-foreground/80 leading-relaxed font-serif italic">
                  &ldquo;{displayedQuote}&rdquo;
                </p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                    Source: {sourceLabel}
                    {citation?.section_title
                      ? ` - ${citation.section_title}`
                      : ""}
                  </p>
                  {citation?.document_url && (
                    <a
                      href={citation.document_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[10px] uppercase tracking-widest font-bold text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Open source
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function WatchOutFor({ cases }: WatchOutForProps) {
  if (cases.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <AlertTriangle
            className="h-5 w-5 text-foreground"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Watch Out For
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
          Worst first
        </span>
      </div>

      <div className="divide-y divide-border">
        {cases.map((item, index) => (
          <WatchOutCard
            key={`${item.title ?? "case"}-${index}`}
            item={item}
            index={index}
          />
        ))}
      </div>
    </div>
  );
}
