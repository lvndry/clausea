"use client";

import { Database, Network } from "lucide-react";

import { cn } from "@/lib/utils";

import {
  type ConsumerCase,
  type ConsumerDataItem,
  asConsumerCase,
  asDataItem,
  normalizeSeverity,
} from "./types";

const severityStyle: Record<string, { color: string; border: string }> = {
  critical: { color: "text-risk-high", border: "border-risk-high/30" },
  high: { color: "text-risk-high", border: "border-risk-high/30" },
  medium: { color: "text-risk-medium", border: "border-risk-medium/30" },
  low: { color: "text-muted-foreground", border: "border-border" },
};

function severityFor(raw: string | null | undefined) {
  return severityStyle[normalizeSeverity(raw)] ?? severityStyle.low;
}

const LINKAGE_LABEL: Record<string, string> = {
  linked_to_you: "Linked to you",
  linked_to_device: "Linked to device",
  not_linked: "Not linked",
};

function linkageLabel(raw: string | null | undefined): string | null {
  const key = (raw ?? "").trim().toLowerCase();
  return LINKAGE_LABEL[key] ?? null;
}

export function WhatTheyCollect({
  items,
}: {
  items: Array<ConsumerDataItem | string>;
}) {
  if (items.length === 0) return null;
  const buckets = items.map(asDataItem).filter((item) => item.title);
  if (buckets.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Database
            className="h-5 w-5 text-foreground"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            What They Collect
          </h3>
        </div>
        <span className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-bold bg-muted/5">
          {buckets.length} types
        </span>
      </div>

      <div className="grid grid-cols-1 divide-y divide-border sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-3 [&>*]:border-b [&>*]:border-border sm:[&>*:nth-child(odd)]:border-r lg:[&>*:nth-child(odd)]:border-r-0 lg:[&>*:not(:nth-child(3n))]:border-r">
        {buckets.map((item, index) => {
          const style = severityFor(item.severity);
          const detail = item.why ?? item.means_for_you;
          const linkage = linkageLabel(item.linkage_tier);

          return (
            <div
              key={`${item.title}-${index}`}
              className="p-6 flex flex-col gap-3 hover:bg-muted/5 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-display font-medium text-base text-foreground leading-snug">
                  {item.title}
                </span>
                {item.severity && (
                  <span
                    className={cn(
                      "px-2 py-0.5 border text-[8px] uppercase tracking-widest font-bold shrink-0",
                      style.color,
                      style.border,
                    )}
                  >
                    {normalizeSeverity(item.severity)}
                  </span>
                )}
              </div>
              {detail && (
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {detail}
                </p>
              )}
              {(linkage || item.sold) && (
                <div className="flex flex-wrap gap-2">
                  {linkage && (
                    <span className="px-2 py-0.5 border border-border text-[8px] uppercase tracking-widest font-medium text-muted-foreground">
                      {linkage}
                    </span>
                  )}
                  {item.sold && (
                    <span className="px-2 py-0.5 border border-risk-high/30 text-[8px] uppercase tracking-widest font-bold text-risk-high">
                      Sold / shared for value
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function WhoGetsYourData({
  items,
}: {
  items: Array<ConsumerCase | string>;
}) {
  if (items.length === 0) return null;
  const recipients = items.map(asConsumerCase).filter((item) => item.title);
  if (recipients.length === 0) return null;

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Network
            className="h-5 w-5 text-foreground"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Who Gets Your Data
          </h3>
        </div>
        <span className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-bold bg-muted/5">
          {recipients.length} recipients
        </span>
      </div>

      <div className="divide-y divide-border">
        {recipients.map((item, index) => {
          const purpose = item.why ?? item.means_for_you;
          return (
            <div
              key={`${item.title}-${index}`}
              className="grid grid-cols-1 md:grid-cols-12 hover:bg-muted/5 transition-colors"
            >
              <div className="col-span-12 md:col-span-4 p-6 border-b md:border-b-0 md:border-r border-border bg-muted/5">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground block mb-2">
                  Recipient
                </span>
                <h4 className="font-display font-medium text-lg text-foreground leading-snug">
                  {item.title}
                </h4>
              </div>
              <div className="col-span-12 md:col-span-8 p-6 space-y-4">
                {purpose && (
                  <p className="text-sm text-foreground/80 leading-relaxed">
                    {purpose}
                  </p>
                )}
                {item.what_they_get && (
                  <div className="flex flex-wrap gap-2">
                    <span className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                      {item.what_they_get}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
