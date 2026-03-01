"use client";

import {
  AlertTriangle,
  CheckCircle,
  Shield,
  Sparkles,
  ThumbsUp,
  Zap,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface YourPowerProps {
  rights?: string[] | null;
  dangers?: string[] | null;
  benefits?: string[] | null;
}

export function YourPower({ rights, dangers, benefits }: YourPowerProps) {
  const hasRights = rights && rights.length > 0;
  const hasDangers = dangers && dangers.length > 0;
  const hasBenefits = benefits && benefits.length > 0;

  if (!hasRights && !hasDangers && !hasBenefits) {
    return null;
  }

  const positiveItems = [
    ...(rights?.slice(0, 3).map((r) => ({ type: "right", text: r })) || []),
    ...(benefits?.slice(0, 2).map((b) => ({ type: "benefit", text: b })) || []),
  ];

  const negativeItems = dangers?.slice(0, 5) || [];

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-foreground" strokeWidth={1.5} />
          <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
            Analysis of Rights & Risks
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2">
        {/* Rights & Benefits Column */}
        <div className="border-b md:border-b-0 md:border-r border-border">
          <div className="p-6 border-b border-border bg-muted/5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-widest font-bold text-[#2B7A5C]">
                Rights & Benefits
              </span>
              <ThumbsUp className="h-4 w-4 text-[#2B7A5C]/40" />
            </div>
          </div>
          <div className="divide-y divide-border">
            {positiveItems.length > 0 ? (
              positiveItems.map((item, index) => (
                <div
                  key={index}
                  className="p-6 flex items-start gap-4 hover:bg-muted/5 transition-colors"
                >
                  <div className="mt-1 shrink-0">
                    {item.type === "right" ? (
                      <Shield
                        className="h-4 w-4 text-[#2B7A5C]"
                        strokeWidth={1.5}
                      />
                    ) : (
                      <Sparkles
                        className="h-4 w-4 text-[#2B7A5C]"
                        strokeWidth={1.5}
                      />
                    )}
                  </div>
                  <span className="text-sm text-foreground leading-relaxed">
                    {item.text}
                  </span>
                </div>
              ))
            ) : (
              <div className="p-10 text-center text-xs text-muted-foreground uppercase tracking-widest">
                No specific rights identified
              </div>
            )}
          </div>
        </div>

        {/* Limitations & Concerns Column */}
        <div className="flex flex-col">
          <div className="p-6 border-b border-border bg-muted/5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-widest font-bold text-[#BD452D]">
                Limitations & Concerns
              </span>
              <AlertTriangle className="h-4 w-4 text-[#BD452D]/40" />
            </div>
          </div>
          <div className="divide-y divide-border flex-1">
            {negativeItems.length > 0 ? (
              negativeItems.map((danger, index) => (
                <div
                  key={index}
                  className="p-6 flex items-start gap-4 hover:bg-muted/5 transition-colors"
                >
                  <div className="mt-1 shrink-0">
                    <AlertTriangle
                      className="h-4 w-4 text-[#BD452D]"
                      strokeWidth={1.5}
                    />
                  </div>
                  <span className="text-sm text-foreground leading-relaxed">
                    {danger}
                  </span>
                </div>
              ))
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-10">
                <CheckCircle
                  className="h-8 w-8 text-[#2B7A5C] mb-4"
                  strokeWidth={1.5}
                />
                <span className="text-xs text-[#2B7A5C] uppercase tracking-widest font-bold">
                  No critical concerns identified
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
