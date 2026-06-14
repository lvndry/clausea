"use client";

import { Database, Network } from "lucide-react";

import { cn } from "@/lib/utils";

import {
  type ConsumerDataItem,
  type ConsumerRecipient,
  asDataItem,
  asRecipient,
  normalizeSeverity,
} from "./types";

const sensitivityStyle: Record<string, { color: string; border: string }> = {
  sensitive: { color: "text-[#BD452D]", border: "border-[#BD452D]/30" },
  high: { color: "text-[#BD452D]", border: "border-[#BD452D]/30" },
  medium: { color: "text-[#B58D2D]", border: "border-[#B58D2D]/30" },
  low: { color: "text-muted-foreground", border: "border-border" },
};

function sensitivityFor(raw: string | null | undefined) {
  const key = (raw ?? "").trim().toLowerCase();
  return sensitivityStyle[key] ?? sensitivityStyle.low;
}

export function WhatTheyCollect({
  items,
}: {
  items: Array<ConsumerDataItem | string>;
}) {
  if (items.length === 0) return null;
  const buckets = items.map(asDataItem).filter((item) => item.label);
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
          const sensitivity = item.sensitivity
            ? normalizeSeverity(item.sensitivity)
            : null;
          const style = sensitivityFor(item.sensitivity);

          return (
            <div
              key={`${item.label}-${index}`}
              className="p-6 flex flex-col gap-3 hover:bg-muted/5 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-display font-medium text-base text-foreground leading-snug">
                  {item.label}
                </span>
                {sensitivity && (
                  <span
                    className={cn(
                      "px-2 py-0.5 border text-[8px] uppercase tracking-widest font-bold shrink-0",
                      style.color,
                      style.border,
                    )}
                  >
                    {sensitivity}
                  </span>
                )}
              </div>
              {item.detail && (
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {item.detail}
                </p>
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
  items: Array<ConsumerRecipient | string>;
}) {
  if (items.length === 0) return null;
  const recipients = items.map(asRecipient).filter((item) => item.recipient);
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
        {recipients.map((item, index) => (
          <div
            key={`${item.recipient}-${index}`}
            className="grid grid-cols-1 md:grid-cols-12 hover:bg-muted/5 transition-colors"
          >
            <div className="col-span-12 md:col-span-4 p-6 border-b md:border-b-0 md:border-r border-border bg-muted/5">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground block mb-2">
                Recipient
              </span>
              <h4 className="font-display font-medium text-lg text-foreground leading-snug">
                {item.recipient}
              </h4>
            </div>
            <div className="col-span-12 md:col-span-8 p-6 space-y-4">
              {item.purpose && (
                <p className="text-sm text-foreground/80 leading-relaxed">
                  {item.purpose}
                </p>
              )}
              {item.data_shared && item.data_shared.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {item.data_shared.map((data, dataIndex) => (
                    <span
                      key={`${data}-${dataIndex}`}
                      className="px-3 py-1 border border-border text-[10px] uppercase tracking-widest font-medium text-muted-foreground"
                    >
                      {data}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
