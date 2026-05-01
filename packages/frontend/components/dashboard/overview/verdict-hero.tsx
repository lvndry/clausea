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

import MarkdownRenderer from "@/components/markdown/markdown-renderer";
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
    label: "LOW RISK",
    subtitle: "Your privacy is well protected",
    color: "text-[#2B7A5C]",
    border: "border-[#2B7A5C]/20",
    bg: "bg-[#2B7A5C]/5",
    icon: ShieldCheck,
  },
  user_friendly: {
    label: "FAIR",
    subtitle: "Generally respects your privacy",
    color: "text-[#2B7A5C]",
    border: "border-[#2B7A5C]/20",
    bg: "bg-[#2B7A5C]/5",
    icon: CheckCircle,
  },
  moderate: {
    label: "MIXED",
    subtitle: "Some privacy considerations",
    color: "text-[#B58D2D]",
    border: "border-[#B58D2D]/20",
    bg: "bg-[#B58D2D]/5",
    icon: Shield,
  },
  pervasive: {
    label: "PERVASIVE",
    subtitle: "Significant privacy concerns",
    color: "text-[#BD452D]",
    border: "border-[#BD452D]/20",
    bg: "bg-[#BD452D]/5",
    icon: ShieldAlert,
  },
  very_pervasive: {
    label: "CRITICAL",
    subtitle: "Major privacy risks identified",
    color: "text-[#BD452D]",
    border: "border-[#BD452D]/20",
    bg: "bg-[#BD452D]/5",
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
    if (riskScore <= 3) return "text-[#2B7A5C]";
    if (riskScore <= 6) return "text-[#B58D2D]";
    return "text-[#BD452D]";
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
    <div className="grid grid-cols-1 md:grid-cols-12 border border-border bg-background">
      {/* Score and Verdict */}
      <div className="col-span-12 md:col-span-4 p-8 border-b md:border-b-0 md:border-r border-border flex flex-col justify-between">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground block mb-6">
            Privacy Verdict
          </span>
          <h1
            className={cn(
              "text-5xl md:text-6xl font-display font-medium leading-[0.9] tracking-tight mb-4",
              config.color,
            )}
          >
            {config.label}
          </h1>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-display font-medium text-foreground">
              {riskScore}
            </span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Risk Score
            </span>
          </div>
        </div>

        <div className="mt-12">
          <p className="text-xs uppercase tracking-[0.2em] font-medium text-foreground mb-3">
            Status
          </p>
          <div
            className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 border border-border text-[10px] uppercase tracking-widest font-bold",
              config.color,
              config.bg,
            )}
          >
            <Icon className="h-3 w-3" />
            {config.label}
          </div>
        </div>
      </div>

      {/* Analysis and Insights */}
      <div className="col-span-12 md:col-span-8 flex flex-col">
        <div className="p-8 md:p-10 border-b border-border flex-1">
          <span className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground block mb-6">
            Executive Analysis
          </span>
          <div className="text-lg text-foreground leading-relaxed max-w-2xl prose prose-slate dark:prose-invert">
            <MarkdownRenderer>{summary}</MarkdownRenderer>
          </div>
          <div className="mt-8">
            <Button
              variant="outline"
              size="sm"
              onClick={handleShare}
              className="gap-2 rounded-none border-foreground text-foreground uppercase text-[10px] tracking-widest font-bold px-6 h-10 hover:bg-foreground hover:text-background transition-colors"
            >
              <Share2 className="h-3 w-3" />
              {shareText}
            </Button>
          </div>
        </div>

        {/* Key Insights */}
        {topKeypoints.length > 0 && (
          <div className="p-8 md:p-10 bg-muted/5">
            <span className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground block mb-6">
              Key Insights
            </span>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {topKeypoints.map((point, index) => (
                <div key={index} className="space-y-3">
                  <div
                    className={cn(
                      "h-px w-8",
                      config.color.replace("text-", "bg-"),
                    )}
                  />
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {point}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
