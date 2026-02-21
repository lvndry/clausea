"use client";

import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  ExternalLink,
  FileSearch,
  FileText,
  BarChart3,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useCallback } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface PipelineStep {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  message: string | null;
}

interface PipelineJobData {
  id: string;
  product_slug: string;
  product_name: string;
  url: string;
  status: string;
  steps: PipelineStep[];
  error: string | null;
  documents_found: number;
  documents_stored: number;
}

interface PipelineProgressProps {
  jobId: string;
  onComplete?: (productSlug: string) => void;
  onDismiss?: () => void;
}

const STEP_CONFIG: Record<
  string,
  { label: string; icon: typeof FileSearch; description: string }
> = {
  crawling: {
    label: "Discovering Documents",
    icon: FileSearch,
    description: "Scanning website for legal documents",
  },
  summarizing: {
    label: "Analyzing Content",
    icon: FileText,
    description: "AI analysis of privacy practices",
  },
  generating_overview: {
    label: "Building Overview",
    icon: BarChart3,
    description: "Generating privacy assessment",
  },
};

function StepIndicator({ step }: { step: PipelineStep }) {
  const config = STEP_CONFIG[step.name] || {
    label: step.name,
    icon: Circle,
    description: "",
  };
  const StepIcon = config.icon;

  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5">
        {step.status === "completed" ? (
          <CheckCircle2 className="h-5 w-5 text-green-500" />
        ) : step.status === "running" ? (
          <Loader2 className="h-5 w-5 text-primary animate-spin" />
        ) : step.status === "failed" ? (
          <XCircle className="h-5 w-5 text-destructive" />
        ) : (
          <Circle className="h-5 w-5 text-muted-foreground/30" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <StepIcon
            className={cn(
              "h-3.5 w-3.5",
              step.status === "running"
                ? "text-primary"
                : step.status === "completed"
                  ? "text-green-500"
                  : step.status === "failed"
                    ? "text-destructive"
                    : "text-muted-foreground/50",
            )}
          />
          <span
            className={cn(
              "text-sm font-medium",
              step.status === "running"
                ? "text-foreground"
                : step.status === "completed"
                  ? "text-green-600"
                  : step.status === "failed"
                    ? "text-destructive"
                    : "text-muted-foreground",
            )}
          >
            {config.label}
          </span>
        </div>
        {step.message && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
            {step.message}
          </p>
        )}
        {step.status === "pending" && (
          <p className="text-xs text-muted-foreground/50 mt-0.5">
            {config.description}
          </p>
        )}
      </div>
    </div>
  );
}

export function PipelineProgress({
  jobId,
  onComplete,
  onDismiss,
}: PipelineProgressProps) {
  const router = useRouter();
  const [job, setJob] = useState<PipelineJobData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isTerminal =
    job?.status === "completed" || job?.status === "failed";

  const pollJob = useCallback(async () => {
    try {
      const res = await fetch(`/api/pipeline/jobs/${jobId}`);
      if (!res.ok) {
        throw new Error("Failed to fetch job status");
      }
      const data: PipelineJobData = await res.json();
      setJob(data);

      if (data.status === "completed" || data.status === "failed") {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        if (data.status === "completed" && onComplete) {
          onComplete(data.product_slug);
        }
      }
    } catch (err) {
      console.error("Error polling pipeline job:", err);
      setError(err instanceof Error ? err.message : "Failed to check status");
    }
  }, [jobId, onComplete]);

  useEffect(() => {
    // Initial fetch
    pollJob();

    // Poll every 3 seconds
    intervalRef.current = setInterval(pollJob, 3000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [pollJob]);

  if (error && !job) {
    return (
      <Card variant="default" className="border-destructive/50">
        <CardContent className="p-5">
          <div className="text-center space-y-2">
            <XCircle className="h-8 w-8 text-destructive mx-auto" />
            <p className="text-sm text-destructive font-medium">{error}</p>
            {onDismiss && (
              <Button variant="ghost" size="sm" onClick={onDismiss}>
                Dismiss
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!job) {
    return (
      <Card variant="default">
        <CardContent className="p-5">
          <div className="flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="text-sm text-muted-foreground">
              Starting analysis...
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const completedSteps = job.steps.filter(
    (s) => s.status === "completed",
  ).length;
  const progress = (completedSteps / job.steps.length) * 100;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
      >
        <Card
          variant="default"
          className={cn(
            "transition-all duration-300",
            job.status === "completed" && "border-green-500/50",
            job.status === "failed" && "border-destructive/50",
          )}
        >
          <CardContent className="p-5 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <h3 className="text-sm font-bold font-display text-foreground">
                  {job.status === "completed"
                    ? `${job.product_name} is ready`
                    : job.status === "failed"
                      ? `Analysis failed for ${job.product_name}`
                      : `Analyzing ${job.product_name}...`}
                </h3>
                <p className="text-xs text-muted-foreground truncate max-w-xs">
                  {job.url}
                </p>
              </div>
              {onDismiss && isTerminal && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onDismiss}
                  className="text-xs"
                >
                  Dismiss
                </Button>
              )}
            </div>

            {/* Progress bar */}
            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className={cn(
                  "h-full rounded-full",
                  job.status === "failed"
                    ? "bg-destructive"
                    : job.status === "completed"
                      ? "bg-green-500"
                      : "bg-primary",
                )}
              />
            </div>

            {/* Steps */}
            <div className="space-y-3">
              {job.steps.map((step) => (
                <StepIndicator key={step.name} step={step} />
              ))}
            </div>

            {/* Error message */}
            {job.error && (
              <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                {job.error}
              </p>
            )}

            {/* Stats */}
            {job.documents_stored > 0 && (
              <p className="text-xs text-muted-foreground">
                {job.documents_stored} legal document
                {job.documents_stored !== 1 ? "s" : ""} found
              </p>
            )}

            {/* Actions */}
            {job.status === "completed" && (
              <Button
                size="sm"
                className="w-full rounded-lg"
                onClick={() => router.push(`/products/${job.product_slug}`)}
              >
                View Analysis
                <ExternalLink className="ml-2 h-3.5 w-3.5" />
              </Button>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}
