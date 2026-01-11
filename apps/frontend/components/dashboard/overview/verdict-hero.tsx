"use client";

import {
  AlertTriangle,
  CheckCircle,
  Share2,
  Shield,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useParams } from "next/navigation";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface VerdictHeroProps {
  productName: string;
  companyName?: string | null;
  verdict:
    | "very_user_friendly"
    | "user_friendly"
    | "moderate"
    | "pervasive"
    | "very_pervasive";
  riskScore: number;
  summary: string;
  keypoints?: string[] | null;
}

const verdictConfig = {
  very_user_friendly: {
    label: "Very User Friendly",
    subtitle: "Your privacy is well protected",
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-50/30 dark:bg-emerald-950/10",
    icon: ShieldCheck,
  },
  user_friendly: {
    label: "User Friendly",
    subtitle: "Generally respects your privacy",
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50/30 dark:bg-green-950/10",
    icon: CheckCircle,
  },
  moderate: {
    label: "Moderate",
    subtitle: "Some privacy considerations",
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-50/30 dark:bg-amber-950/10",
    icon: Shield,
  },
  pervasive: {
    label: "Pervasive",
    subtitle: "Significant privacy concerns",
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-50/30 dark:bg-orange-950/10",
    icon: ShieldAlert,
  },
  very_pervasive: {
    label: "Very Pervasive",
    subtitle: "Major privacy risks identified",
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-50/30 dark:bg-red-950/10",
    icon: AlertTriangle,
  },
};

export function VerdictHero({
  productName,
  companyName,
  verdict,
  riskScore,
  summary,
  keypoints,
}: VerdictHeroProps) {
  const params = useParams();
  const slug = params.slug as string;
  const config = verdictConfig[verdict];
  const Icon = config.icon;
  const topKeypoints = keypoints?.slice(0, 3) || [];
  const [shareText, setShareText] = useState("Share");

  const getRiskLabel = () => {
    if (riskScore <= 3) return "Low";
    if (riskScore <= 6) return "Moderate";
    return "High";
  };

  const getRiskColor = () => {
    if (riskScore <= 3) return "text-emerald-600 dark:text-emerald-400";
    if (riskScore <= 6) return "text-amber-600 dark:text-amber-400";
    return "text-red-600 dark:text-red-400";
  };

  const handleShare = async () => {
    const shareUrl = `https://clausea.co/products/${slug}`;
    const shareMessage = `${productName} is rated "${config.label}" for privacy (${riskScore}/10 risk). Check out the full analysis:`;

    // Try native share API first (mobile)
    if (navigator.share) {
      try {
        await navigator.share({
          title: `${productName} Privacy Analysis - Clausea`,
          text: shareMessage,
          url: shareUrl,
        });
        return;
      } catch {
        // User cancelled or share failed, fall through to clipboard
      }
    }

    // Fallback to clipboard
    try {
      await navigator.clipboard.writeText(`${shareMessage} ${shareUrl}`);
      setShareText("Copied!");
      setTimeout(() => setShareText("Share"), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement("textarea");
      textArea.value = `${shareMessage} ${shareUrl}`;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setShareText("Copied!");
      setTimeout(() => setShareText("Share"), 2000);
    }
  };

  return (
    <div className="space-y-8">
      {/* Main Verdict Section */}
      <div className="space-y-5">
        {/* Verdict Header - Better aligned */}
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "w-8 h-8 rounded-md flex items-center justify-center shrink-0 mt-0.5",
              config.bg,
            )}
          >
            <Icon className={cn("h-4 w-4", config.color)} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-3 flex-wrap">
              <h1
                className={cn(
                  "text-3xl md:text-4xl font-bold font-display tracking-tight",
                  config.color,
                )}
              >
                {config.label}
              </h1>
              <span className="text-lg font-medium text-muted-foreground">
                {riskScore}/10
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-1.5">
              {config.subtitle}
            </p>
          </div>
        </div>

        {/* Summary - Readable size */}
        <div className="pl-11 pr-4 md:pr-24">
          <p className="text-base text-foreground leading-relaxed">{summary}</p>
        </div>

        {/* Risk Info + Share - Clean, aligned */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pl-11 pt-1 gap-3 sm:gap-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Risk
            </span>
            <span className={cn("text-sm font-semibold", getRiskColor())}>
              {getRiskLabel()}
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleShare}
            className="gap-2"
          >
            <Share2 className="h-4 w-4" />
            {shareText}
          </Button>
        </div>
      </div>

      {/* Key Insights - Clean, readable */}
      {topKeypoints.length > 0 && (
        <div className="space-y-3 pt-6 border-t border-border/50 pl-11 pr-4">
          <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Key Insights
          </h3>
          <div className="space-y-2.5">
            {topKeypoints.map((point, index) => (
              <div
                key={index}
                className="flex items-start gap-2.5 text-sm text-foreground/90 leading-relaxed"
              >
                <span
                  className={cn(
                    "mt-1.5 h-1 w-1 rounded-full shrink-0",
                    config.color.replace("text-", "bg-"),
                  )}
                />
                <span>{point}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
