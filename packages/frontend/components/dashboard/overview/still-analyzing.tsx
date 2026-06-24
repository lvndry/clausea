"use client";

import { Shield } from "lucide-react";

export function StillAnalyzing() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-12 border border-border bg-background min-h-[320px]">
      <div className="col-span-12 flex flex-col items-center justify-center text-center p-12 md:p-16">
        <div className="relative mb-8">
          <div className="absolute inset-0 animate-ping rounded-full bg-foreground/5" />
          <div className="relative flex items-center justify-center h-16 w-16 rounded-full border border-border bg-muted/5">
            <Shield
              className="h-7 w-7 text-muted-foreground animate-pulse"
              strokeWidth={1.5}
            />
          </div>
        </div>

        <h2 className="text-xl md:text-2xl font-display font-medium text-foreground mb-3">
          We&apos;re still analyzing this product&apos;s privacy policies.
        </h2>

        <p className="text-sm text-muted-foreground leading-relaxed max-w-md">
          This usually takes a few minutes. Check back soon or we&apos;ll notify
          you when it&apos;s ready.
        </p>
      </div>
    </div>
  );
}
