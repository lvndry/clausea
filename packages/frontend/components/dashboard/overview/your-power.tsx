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
    <Card variant="default" className="border-border">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
            <Zap className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <CardTitle className="text-lg">Your Power</CardTitle>
            <p className="text-sm text-muted-foreground mt-0.5">
              Rights, benefits, and concerns to be aware of
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid md:grid-cols-2 gap-6">
          {/* Positive Column */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                <Shield className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <h4 className="font-semibold text-emerald-600 dark:text-emerald-400">
                Your Rights & Benefits
              </h4>
            </div>

            <div className="space-y-2">
              {positiveItems.length > 0 ? (
                positiveItems.map((item, index) => (
                  <div
                    key={index}
                    className={cn(
                      "flex items-start gap-2.5 p-3 rounded-lg border",
                      item.type === "right"
                        ? "bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800"
                        : "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800",
                    )}
                  >
                    <div
                      className={cn(
                        "w-5 h-5 rounded-md flex items-center justify-center shrink-0 mt-0.5",
                        item.type === "right"
                          ? "bg-emerald-100 dark:bg-emerald-900/30"
                          : "bg-blue-100 dark:bg-blue-900/30",
                      )}
                    >
                      {item.type === "right" ? (
                        <CheckCircle className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <ThumbsUp className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                      )}
                    </div>
                    <span className="text-sm text-foreground leading-snug">
                      {item.text}
                    </span>
                  </div>
                ))
              ) : (
                <div className="flex items-center justify-center p-6 rounded-lg bg-muted/30 border border-dashed border-border">
                  <p className="text-sm text-muted-foreground">
                    No specific rights documented
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Negative Column */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
              </div>
              <h4 className="font-semibold text-amber-600 dark:text-amber-400">
                Limitations & Concerns
              </h4>
            </div>

            <div className="space-y-2">
              {negativeItems.length > 0 ? (
                negativeItems.map((danger, index) => (
                  <div
                    key={index}
                    className={cn(
                      "flex items-start gap-2.5 p-3 rounded-lg border",
                      "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800",
                    )}
                  >
                    <div className="w-5 h-5 rounded-md bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center shrink-0 mt-0.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                    </div>
                    <span className="text-sm text-foreground leading-snug">
                      {danger}
                    </span>
                  </div>
                ))
              ) : (
                <div className="flex items-center justify-center p-6 rounded-lg bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800">
                  <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                    <Sparkles className="h-4 w-4" />
                    <p className="text-sm font-medium">
                      No major concerns identified
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
