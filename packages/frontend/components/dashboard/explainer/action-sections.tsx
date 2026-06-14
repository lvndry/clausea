"use client";

import {
  ArrowRight,
  GitCompareArrows,
  Globe,
  HelpCircle,
  Info,
  Lightbulb,
} from "lucide-react";

import { cn } from "@/lib/utils";

import {
  type ActionStep,
  type ConsumerContradiction,
  type ConsumerRegionVerdict,
  type ConsumerSilentTopic,
  asActionStep,
  scopeLabels,
} from "./types";

export function WhatYouCanDo({ items }: { items: Array<ActionStep | string> }) {
  if (items.length === 0) return null;
  const steps = items.map(asActionStep).filter((step) => step.action);
  if (steps.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center gap-3">
        <Lightbulb
          className="h-5 w-5 text-foreground"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
          What You Can Do
        </h3>
      </div>

      <div className="divide-y divide-border">
        {steps.map((step, index) => (
          <div
            key={`${step.action}-${index}`}
            className="p-6 flex items-start gap-4 hover:bg-muted/5 transition-colors"
          >
            <span className="font-display font-medium text-sm text-muted-foreground w-6 shrink-0 mt-0.5">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium text-foreground leading-relaxed">
                  {step.action}
                </span>
                {scopeLabels(step.applies_to).map((label) => (
                  <span
                    key={label}
                    className="inline-flex items-center gap-1 px-2 py-0.5 border border-border text-[8px] uppercase tracking-widest font-bold text-muted-foreground"
                  >
                    <Globe className="h-2.5 w-2.5" aria-hidden="true" />
                    {label}
                  </span>
                ))}
              </div>
            </div>
            <ArrowRight
              className="h-4 w-4 text-muted-foreground/30 shrink-0 mt-0.5"
              aria-hidden="true"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function GoodToKnow({ items }: { items: string[] }) {
  if (items.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center gap-3">
        <Info
          className="h-5 w-5 text-foreground"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
          Good To Know
        </h3>
      </div>
      <div className="divide-y divide-border">
        {items.map((item, index) => (
          <div
            key={`${item}-${index}`}
            className="p-6 flex items-start gap-4 hover:bg-muted/5 transition-colors"
          >
            <span
              className="mt-1.5 h-1.5 w-1.5 bg-risk-low shrink-0"
              aria-hidden="true"
            />
            <p className="text-sm text-foreground/90 leading-relaxed">{item}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// The differentiator: what the document does NOT say, framed as findings.
export function SilentOn({
  items,
}: {
  items: Array<ConsumerSilentTopic | string>;
}) {
  if (items.length === 0) return null;

  return (
    <div className="border border-dashed border-border bg-muted/5">
      <div className="p-6 border-b border-dashed border-border flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <HelpCircle
            className="h-5 w-5 text-foreground"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            What This Document Doesn&apos;t Say
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
          Silence is a signal
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 [&>*]:border-b [&>*]:border-dashed [&>*]:border-border sm:[&>*:nth-child(odd)]:border-r">
        {items.map((item, index) => {
          const topic = typeof item === "string" ? item : item.topic;
          const whyItMatters =
            typeof item === "string" ? null : item.why_it_matters;
          return (
            <div
              key={`${topic}-${index}`}
              className="p-6 flex items-start gap-4"
            >
              <span className="font-display text-lg text-muted-foreground/50 leading-none shrink-0">
                ?
              </span>
              <div>
                <p className="text-sm text-foreground/80 leading-relaxed">
                  {topic}
                </p>
                {whyItMatters && (
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                    {whyItMatters}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Conflicts({ items }: { items: ConsumerContradiction[] }) {
  if (items.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center gap-3">
        <GitCompareArrows
          className="h-5 w-5 text-foreground"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
          Where Their Documents Disagree
        </h3>
      </div>
      <div className="divide-y divide-border">
        {items.map((item, index) => (
          <div
            key={`${item.topic ?? "conflict"}-${index}`}
            className="p-6 space-y-4"
          >
            {item.topic && (
              <h4 className="font-display font-medium text-lg text-foreground leading-snug">
                {item.topic}
              </h4>
            )}
            {(item.what_one_doc_says || item.what_another_says) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-border border border-border">
                <div className="bg-background p-4">
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground block mb-1">
                    One document says
                  </span>
                  <span className="text-sm text-foreground">
                    {item.what_one_doc_says ?? "—"}
                  </span>
                </div>
                <div className="bg-background p-4">
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground block mb-1">
                    Another says
                  </span>
                  <span className="text-sm text-foreground">
                    {item.what_another_says ?? "—"}
                  </span>
                </div>
              </div>
            )}
            {item.assume && (
              <p className="text-xs text-muted-foreground leading-relaxed border-l-2 border-risk-medium/40 pl-4">
                Assume the worst case: {item.assume}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function RightsByRegion({
  verdicts,
}: {
  verdicts: ConsumerRegionVerdict[];
}) {
  const regions = verdicts.filter((verdict) => verdict.region);
  if (regions.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center gap-3">
        <Globe
          className="h-5 w-5 text-foreground"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
          Your Rights Depend On Where You Live
        </h3>
      </div>
      <div
        className={cn(
          "grid grid-cols-1",
          regions.length > 1 && "md:grid-cols-2",
        )}
      >
        {regions.map((verdict, index) => (
          <div
            key={`${verdict.region}-${index}`}
            className={cn(
              "p-6 border-b border-border space-y-4",
              regions.length > 1 && index % 2 === 0 && "md:border-r",
            )}
          >
            <span className="inline-flex items-center gap-2 px-3 py-1 border border-foreground text-[10px] uppercase tracking-widest font-bold text-foreground">
              <Globe className="h-3 w-3" aria-hidden="true" />
              {verdict.region}
            </span>
            {verdict.you_can && verdict.you_can.length > 0 && (
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-widest text-risk-low font-medium block">
                  You can
                </span>
                <ul className="space-y-2">
                  {verdict.you_can.map((right, rightIndex) => (
                    <li
                      key={`can-${right}-${rightIndex}`}
                      className="flex items-start gap-3 text-sm text-foreground/80 leading-relaxed"
                    >
                      <span
                        className="mt-1.5 h-1.5 w-1.5 bg-risk-low shrink-0"
                        aria-hidden="true"
                      />
                      {right}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {verdict.you_cannot && verdict.you_cannot.length > 0 && (
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-widest text-risk-high font-medium block">
                  You cannot
                </span>
                <ul className="space-y-2">
                  {verdict.you_cannot.map((right, rightIndex) => (
                    <li
                      key={`cannot-${right}-${rightIndex}`}
                      className="flex items-start gap-3 text-sm text-foreground/80 leading-relaxed"
                    >
                      <span
                        className="mt-1.5 h-1.5 w-1.5 bg-risk-high shrink-0"
                        aria-hidden="true"
                      />
                      {right}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
