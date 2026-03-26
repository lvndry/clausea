"use client";

import {
  BarChart3,
  CheckCircle2,
  Circle,
  ExternalLink,
  FileSearch,
  FileText,
  Loader2,
  ShieldBan,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface PipelineStep {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  message: string | null;
  progress_current?: number | null;
  progress_total?: number | null;
  progress_percent?: number | null;
}

interface CrawlError {
  url: string;
  status_code: number;
  error_message: string | null;
  error_type:
    | "robots_txt_blocked"
    | "http_error"
    | "timeout"
    | "network_error"
    | "content_error"
    | "unknown";
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
  crawl_errors: CrawlError[];
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
    description: "Scanning website for policy documents",
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
        {step.progress_percent !== undefined &&
          step.progress_percent !== null &&
          step.status === "running" && (
            <div className="mt-2 space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Progress</span>
                <span>{step.progress_percent}%</span>
              </div>
              <div className="w-full bg-muted rounded-full h-1.5">
                <div
                  className="bg-primary h-1.5 rounded-full transition-all duration-300 ease-in-out"
                  style={{ width: `${Math.min(step.progress_percent, 100)}%` }}
                />
              </div>
            </div>
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

function crawlErrorLabel(errorType: CrawlError["error_type"]): string {
  switch (errorType) {
    case "robots_txt_blocked":
      return "Blocked by robots.txt";
    case "http_error":
      return "HTTP error";
    case "timeout":
      return "Request timed out";
    case "network_error":
      return "Network error";
    case "content_error":
      return "Content error";
    default:
      return "Unknown error";
  }
}

function CrawlErrorsDisplay({ errors }: { errors: CrawlError[] }) {
  const robotsBlocked = errors.filter(
    (e) => e.error_type === "robots_txt_blocked",
  );
  const otherErrors = errors.filter(
    (e) => e.error_type !== "robots_txt_blocked",
  );
  const allBlocked =
    robotsBlocked.length > 0 && robotsBlocked.length === errors.length;

  return (
    <div className="space-y-2">
      {allBlocked ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
          <ShieldBan className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div className="space-y-1">
            <p className="text-xs font-medium text-amber-700">
              Site blocked by robots.txt
            </p>
            <p className="text-xs text-amber-600/80">
              This website restricts automated access. We were unable to crawl
              any policy documents. You may need to review their policies
              manually.
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2.5 space-y-2">
          <p className="text-xs font-medium text-destructive">
            {errors.length} URL{errors.length !== 1 ? "s" : ""} failed during
            crawling
          </p>
          {robotsBlocked.length > 0 && (
            <p className="text-xs text-amber-600">
              {robotsBlocked.length} blocked by robots.txt
            </p>
          )}
          <ul className="space-y-1">
            {otherErrors.slice(0, 3).map((err) => (
              <li key={err.url} className="text-xs text-muted-foreground">
                <span className="font-mono text-[10px] break-all">
                  {err.url}
                </span>
                <span className="ml-1 text-destructive/70">
                  — {crawlErrorLabel(err.error_type)}
                </span>
              </li>
            ))}
            {otherErrors.length > 3 && (
              <li className="text-xs text-muted-foreground">
                ...and {otherErrors.length - 3} more
              </li>
            )}
          </ul>
        </div>
      )}
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
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef<number | null>(null);

  const isTerminal = job?.status === "completed" || job?.status === "failed";

  const clearScheduledPoll = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const computePollDelayMs = useCallback(() => {
    const startedAt = startedAtRef.current ?? Date.now();
    const elapsedMs = Date.now() - startedAt;

    // 0–60s: 3s (snappy)
    // 60s–5m: 10s (reduce load)
    // 5m+: 30s (long-running jobs)
    if (elapsedMs >= 5 * 60 * 1000) return 30_000;
    if (elapsedMs >= 60 * 1000) return 10_000;
    return 3_000;
  }, []);

  const pollJob = useCallback(async () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      // Pause polling in background tabs.
      return;
    }
    if (inFlightRef.current) return;

    try {
      inFlightRef.current = true;

      if (!startedAtRef.current) startedAtRef.current = Date.now();

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(`/api/pipeline/jobs/${jobId}`, {
        signal: controller.signal,
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error("Failed to fetch job status");
      }
      const data: PipelineJobData = await res.json();
      setJob(data);

      if (data.status === "completed" || data.status === "failed") {
        clearScheduledPoll();
        if (data.status === "completed" && onComplete) {
          onComplete(data.product_slug);
        }
        return;
      }

      clearScheduledPoll();
      timeoutRef.current = setTimeout(() => {
        void pollJob();
      }, computePollDelayMs());
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      console.error("Error polling pipeline job:", err);
      setError(err instanceof Error ? err.message : "Failed to check status");
      clearScheduledPoll();
      timeoutRef.current = setTimeout(() => {
        void pollJob();
      }, 10_000);
    } finally {
      inFlightRef.current = false;
    }
  }, [
    jobId,
    onComplete,
    clearScheduledPoll,
    computePollDelayMs,
  ]);

  useEffect(() => {
    startedAtRef.current = null;
    setError(null);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void pollJob();
      } else {
        clearScheduledPoll();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    // Initial fetch (and subsequent polls are scheduled dynamically)
    void pollJob();

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      clearScheduledPoll();
      abortRef.current?.abort();
    };
  }, [clearScheduledPoll, pollJob]);

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

            {/* Crawl errors detail */}
            {job.crawl_errors && job.crawl_errors.length > 0 && (
              <CrawlErrorsDisplay errors={job.crawl_errors} />
            )}

            {/* Error message (only if no crawl errors already shown) */}
            {job.error &&
              !(job.crawl_errors && job.crawl_errors.length > 0) && (
                <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                  {job.error}
                </p>
              )}

            {/* Stats */}
            {job.documents_stored > 0 && (
              <p className="text-xs text-muted-foreground">
                {job.documents_stored} policy document
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
