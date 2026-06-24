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
import { gradeToneStyle, parseLetterGrade } from "@/lib/grade";
import { cn } from "@/lib/utils";

interface VerdictHeroProps {
  productName: string;
  companyName?: string | null;
  verdict?:
    | "very_user_friendly"
    | "user_friendly"
    | "moderate"
    | "pervasive"
    | "very_pervasive"
    | null;
  grade?: "A" | "B" | "C" | "D" | "E" | null;
  gradeJustification?: string | null;
  summary: string;
  keypoints?: string[] | null;
}

const verdictConfig = {
  very_user_friendly: {
    label: "LOW RISK",
    subtitle: "Your privacy is well protected",
    color: "text-risk-low",
    border: "border-risk-low/20",
    bg: "bg-risk-low/5",
    icon: ShieldCheck,
  },
  user_friendly: {
    label: "FAIR",
    subtitle: "Generally respects your privacy",
    color: "text-risk-low",
    border: "border-risk-low/20",
    bg: "bg-risk-low/5",
    icon: CheckCircle,
  },
  moderate: {
    label: "MIXED",
    subtitle: "Some privacy considerations",
    color: "text-risk-medium",
    border: "border-risk-medium/20",
    bg: "bg-risk-medium/5",
    icon: Shield,
  },
  pervasive: {
    label: "PERVASIVE",
    subtitle: "Significant privacy concerns",
    color: "text-risk-high",
    border: "border-risk-high/20",
    bg: "bg-risk-high/5",
    icon: ShieldAlert,
  },
  very_pervasive: {
    label: "CRITICAL",
    subtitle: "Major privacy risks identified",
    color: "text-risk-high",
    border: "border-risk-high/20",
    bg: "bg-risk-high/5",
    icon: AlertTriangle,
  },
};

const gradeWord: Record<string, string> = {
  A: "Reassuring",
  B: "Mostly fair",
  C: "Mixed",
  D: "Concerning",
  E: "Alarming",
};

export function VerdictHero({
  productName,
  companyName,
  verdict,
  grade,
  gradeJustification,
  summary,
  keypoints,
}: VerdictHeroProps) {
  const params = useParams();
  const slug = params.slug as string;
  const parsedGrade = grade ? parseLetterGrade(grade) : null;
  const gradeStyle = parsedGrade ? gradeToneStyle(parsedGrade.tone) : null;
  const hasGrade = parsedGrade != null && parsedGrade.letter !== "—";
  const verdictDisplay = hasGrade && verdict ? verdictConfig[verdict] : null;
  const Icon = verdictDisplay?.icon ?? Shield;
  const topKeypoints = keypoints?.slice(0, 3) || [];
  const [shareText, setShareText] = useState("Share");

  const handleShare = async () => {
    const shareUrl = `https://clausea.co/products/${slug}`;
    const shareMessage = hasGrade
      ? `${productName} privacy grade: ${grade} (${gradeWord[grade!] ?? "assessed"}). Full analysis:`
      : `${productName} privacy analysis on Clausea — grade pending:`;

    if (navigator.share) {
      try {
        await navigator.share({
          title: `${productName} Privacy Analysis - Clausea`,
          text: shareMessage,
          url: shareUrl,
        });
        return;
      } catch {
        // fall through
      }
    }

    try {
      await navigator.clipboard.writeText(`${shareMessage} ${shareUrl}`);
      setShareText("Copied!");
      setTimeout(() => setShareText("Share"), 2000);
    } catch {
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
      <div className="col-span-12 md:col-span-4 p-8 border-b md:border-b-0 md:border-r border-border flex flex-col justify-between">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground block mb-6">
            Privacy Grade
          </span>
          <h1
            className={cn(
              "text-5xl md:text-6xl font-display font-medium leading-[0.9] tracking-tight mb-4",
              hasGrade && gradeStyle
                ? gradeStyle.color
                : "text-muted-foreground",
            )}
          >
            {hasGrade ? grade : "—"}
          </h1>
          <div className="space-y-1">
            <p
              className={cn(
                "text-lg font-display font-medium",
                hasGrade && gradeStyle
                  ? gradeStyle.color
                  : "text-muted-foreground",
              )}
            >
              {hasGrade ? (gradeWord[grade!] ?? "Assessed") : "Not yet graded"}
            </p>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Grade A–E
            </span>
          </div>
          {!hasGrade && (
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
              No grade is available yet. Re-run analysis after policy documents
              are indexed, or check back once grading completes.
            </p>
          )}
          {gradeJustification && (
            <p className="mt-4 text-sm text-muted-foreground leading-relaxed border-l-2 border-border pl-4">
              {gradeJustification}
            </p>
          )}
        </div>

        <div className="mt-12">
          <p className="text-xs uppercase tracking-[0.2em] font-medium text-foreground mb-3">
            Status
          </p>
          <div
            className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 border border-border text-[10px] uppercase tracking-widest font-bold",
              hasGrade && verdictDisplay
                ? verdictDisplay.color
                : "text-muted-foreground",
              hasGrade && verdictDisplay ? verdictDisplay.bg : "bg-muted/5",
            )}
          >
            <Icon className="h-3 w-3" />
            {hasGrade && verdictDisplay ? verdictDisplay.label : "Unavailable"}
          </div>
        </div>
      </div>

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
                      hasGrade && gradeStyle
                        ? gradeStyle.color.replace("text-", "bg-")
                        : "bg-muted-foreground/30",
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
