"use client";

import {
  ArrowLeft,
  Calendar,
  FileText,
  LayoutDashboard,
  RotateCcw,
  Shield,
  ShieldBan,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useParams } from "next/navigation";
import posthog from "posthog-js";

import { useEffect, useRef, useState } from "react";

import { ConsumerExplainerView } from "@/components/dashboard/explainer/consumer-explainer-view";
import type { ConsumerExplainer } from "@/components/dashboard/explainer/types";
import { ComplianceBadges } from "@/components/dashboard/overview/compliance-badges";
import { DataStory } from "@/components/dashboard/overview/data-story";
import { PrivacySignals } from "@/components/dashboard/overview/privacy-signals";
import { ScoreBreakdown } from "@/components/dashboard/overview/score-breakdown";
import { SharingMap } from "@/components/dashboard/overview/sharing-map";
import { VerdictHero } from "@/components/dashboard/overview/verdict-hero";
import { YourPower } from "@/components/dashboard/overview/your-power";
import { SourcesList } from "@/components/dashboard/sources-list";
import { PipelineProgress } from "@/components/pipeline/pipeline-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorDisplay } from "@/components/ui/error-display";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { Product } from "@/types";

interface DataPurposeLink {
  data_type: string;
  purposes: string[];
}

interface ThirdPartyRecipient {
  recipient: string;
  data_shared: string[];
  purpose?: string | null;
  risk_level: "low" | "medium" | "high";
}

interface DetailedScore {
  score: number;
  justification: string;
}

interface DetailedScores {
  transparency: DetailedScore;
  data_collection_scope: DetailedScore;
  user_control: DetailedScore;
  third_party_sharing: DetailedScore;
}

interface PrivacySignalsData {
  sells_data: "yes" | "no" | "unclear";
  cross_site_tracking: "yes" | "no" | "unclear";
  account_deletion: "self_service" | "request_required" | "not_specified";
  data_retention_summary?: string | null;
  consent_model: "opt_in" | "opt_out" | "mixed" | "not_specified";
}

interface CoverageItem {
  category: string;
  status: "found" | "missing" | "ambiguous" | "not_analyzed";
  notes?: string | null;
}

interface ComplianceBreakdown {
  score: number;
  status: "Compliant" | "Partially Compliant" | "Non-Compliant" | "Unknown";
  strengths: string[];
  gaps: string[];
}

export interface ProductOverview {
  product_name: string;
  product_slug: string;
  company_name?: string | null;
  last_updated: string;
  verdict:
    | "very_user_friendly"
    | "user_friendly"
    | "moderate"
    | "pervasive"
    | "very_pervasive";
  risk_score: number;
  one_line_summary: string;
  data_collected?: string[] | null;
  data_purposes?: string[] | null;
  data_collection_details?: DataPurposeLink[] | null;
  third_party_details?: ThirdPartyRecipient[] | null;
  your_rights?: string[] | null;
  dangers?: string[] | null;
  benefits?: string[] | null;
  recommended_actions?: string[] | null;
  keypoints?: string[] | null;
  document_counts?: { total: number; analyzed: number; pending: number } | null;
  document_types?: Record<string, number> | null;
  third_party_sharing?: string | null;
  detailed_scores?: DetailedScores | null;
  compliance_status?: Record<string, number> | null;
  compliance?: Record<string, ComplianceBreakdown> | null;
  privacy_signals?: PrivacySignalsData | null;
  coverage?: CoverageItem[] | null;
  contract_clauses?: string[] | null;
}

export interface DocumentSummary {
  id: string;
  title: string | null;
  url: string;
  doc_type?: string;
  last_updated?: string | null;
  verdict?: string | null;
  risk_score?: number | null;
  summary?: string;
  keypoints?: string[];
  keypoints_with_evidence?: Array<{
    keypoint: string;
    evidence: Array<{
      document_id: string;
      url: string;
      content_hash?: string | null;
      quote: string;
      start_char?: number | null;
      end_char?: number | null;
      section_title?: string | null;
    }>;
  }> | null;
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

interface FailedCrawlJob {
  error: string | null;
  crawl_errors: CrawlError[];
  // Stored document count from the crawl. >0 means the crawl succeeded and the
  // failure happened downstream (analysis/overview), so we must not blame the crawl.
  documents_stored?: number;
}

function derivePipelineUrl(product: Product): string | null {
  const fromWebsite = product.website?.trim();
  if (fromWebsite) return fromWebsite;

  const fromCrawlBase =
    Array.isArray(product.crawl_base_urls) && product.crawl_base_urls.length > 0
      ? product.crawl_base_urls[0]?.trim()
      : null;
  if (fromCrawlBase) return fromCrawlBase;

  const fromDomain =
    Array.isArray(product.domains) && product.domains.length > 0
      ? product.domains[0]?.trim()
      : null;
  if (fromDomain) return `https://${fromDomain}`;

  return null;
}

interface CompanyPageProps {
  initialProduct?: Product | null;
  initialData?: ProductOverview | null;
  initialDocuments?: DocumentSummary[];
  initialExplainer?: ConsumerExplainer | null;
}

export default function CompanyPage({
  initialProduct,
  initialData: initialOverview,
  initialDocuments: initialDocs,
  initialExplainer,
}: CompanyPageProps = {}) {
  const params = useParams();
  const slug = params.slug as string;
  const [product, setProduct] = useState<Product | null>(
    initialProduct ?? null,
  );
  const [data, setData] = useState<ProductOverview | null>(
    initialOverview ?? null,
  );
  const [explainer, setExplainer] = useState<ConsumerExplainer | null>(
    initialExplainer ?? null,
  );
  const [documents, setDocuments] = useState<DocumentSummary[]>(
    initialDocs ?? [],
  );
  const [loading, setLoading] = useState(!initialProduct || !initialOverview);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [indexationMode, setIndexationMode] = useState<
    "ready" | "indexing" | "unknown"
  >(initialOverview ? "ready" : "unknown");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [failedJob, setFailedJob] = useState<FailedCrawlJob | null>(null);
  const [emptyJob, setEmptyJob] = useState<FailedCrawlJob | null>(null);
  const [notifyEmail, setNotifyEmail] = useState("");
  const [notifyStatus, setNotifyStatus] = useState<
    "idle" | "submitting" | "success" | "error"
  >("idle");
  const [notifyError, setNotifyError] = useState<string | null>(null);

  useEffect(() => {
    // If SSR pre-loaded both product and overview, skip client-side fetch entirely
    if (initialProduct && initialOverview) {
      setLoading(false);
      return;
    }

    async function fetchData() {
      try {
        setDocumentsLoading(true);

        // Fire all requests in parallel — product, documents, overview, and the
        // consumer explainer arrive together instead of in a sequential chain.
        const [prodRes, docsRes, overviewRes, explainerRes] = await Promise.all(
          [
            fetch(`/api/products/${slug}`),
            fetch(`/api/products/${slug}/documents`),
            fetch(`/api/products/${slug}/overview`),
            fetch(`/api/products/${slug}/explainer`),
          ],
        );

        // The explainer may 404/425 while the product is still indexing — a
        // missing explainer is non-fatal, the overview sections still render.
        if (explainerRes.ok) {
          setExplainer((await explainerRes.json()) as ConsumerExplainer);
        }

        if (!prodRes.ok) {
          setProduct(null);
          setData(null);
          setDocumentsLoading(false);
          setIndexationMode("ready"); // render not-found
          return;
        }
        const prodJson = (await prodRes.json()) as Product;
        setProduct(prodJson);

        const docsJson = docsRes.ok
          ? ((await docsRes.json()) as DocumentSummary[])
          : [];
        setDocuments(docsJson);
        setDocumentsLoading(false);

        // Overview was fetched in parallel — use the result immediately.
        if (overviewRes.ok) {
          setData((await overviewRes.json()) as ProductOverview);
          setIndexationMode("ready");
          return;
        }

        // No overview yet — decide what to show based on the latest pipeline job.
        // The pipeline is auto-triggered ONLY when the product has never been
        // indexed (no job) or a job is still in progress. Terminal jobs are
        // surfaced without retriggering:
        //   - no_documents: crawl finished but found nothing (no retry — a
        //     re-run yields the same result)
        //   - failed: interrupted/errored (offer a manual Retry button)
        setIndexationMode("indexing");
        setData(null);

        const latestRes = await fetch(
          `/api/pipeline/latest?product_slug=${encodeURIComponent(slug)}`,
        );
        const latestJob = latestRes.ok ? await latestRes.json() : null;
        const activeStatuses = [
          "pending",
          "crawling",
          "summarizing",
          "generating_overview",
        ];

        if (latestJob && activeStatuses.includes(latestJob.status)) {
          // A run is already in progress — attach to it (ensurePipelineRunning
          // re-kicks the backend if it isn't currently executing the job).
          setActiveJobId(latestJob.id);
          await ensurePipelineRunning(slug, prodJson);
          return;
        }

        if (latestJob?.status === "no_documents") {
          setEmptyJob({
            error: latestJob.error,
            crawl_errors: latestJob.crawl_errors ?? [],
          });
          return;
        }

        if (latestJob?.status === "failed") {
          setFailedJob({
            error: latestJob.error,
            crawl_errors: latestJob.crawl_errors ?? [],
            documents_stored: latestJob.documents_stored ?? 0,
          });
          return;
        }

        // Auto-trigger ONLY when the product has never been indexed. A `completed`
        // job whose overview momentarily failed to load is a transient fetch issue,
        // not a reason to re-run the whole pipeline — a refresh will pick it up.
        if (!latestJob) {
          await ensurePipelineRunning(slug, prodJson);
        }
      } catch (error) {
        console.error("Failed to fetch product data", error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [slug]);

  /**
   * Ensures a pipeline job is running for the product.
   * First checks for an existing active job (avoids a duplicate POST).
   * Then POSTs /api/pipeline to (re)kick execution when needed (dev reload-safe).
   */
  async function ensurePipelineRunning(productSlug: string, product: Product) {
    const url = derivePipelineUrl(product);

    // 1. Check for an already-running job
    const activeRes = await fetch(
      `/api/pipeline/active?product_slug=${encodeURIComponent(productSlug)}`,
    );
    if (activeRes.ok) {
      const activeJob = (await activeRes.json()) as {
        id?: string;
        status?: string;
      };
      if (activeJob?.id) {
        setActiveJobId(activeJob.id);
        // Dev reload-safe: active jobs can remain in Mongo after backend restarts.
        // POSTing /api/pipeline is idempotent on the backend and will re-kick the runner
        // if it isn't currently executing in this process.
        if (!url) return;
        void fetch("/api/pipeline", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
        return;
      }
    }

    // 2. No active job — start a new one
    if (!url) return;
    const pipelineRes = await fetch("/api/pipeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (pipelineRes.ok) {
      const pipelineJson = await pipelineRes.json();
      setActiveJobId(pipelineJson.job_id ?? null);
    }
  }

  /**
   * Manually re-run the pipeline after a failed/interrupted job.
   * Only offered for `failed` jobs — `no_documents` is a deterministic terminal
   * result that a re-run would not change.
   */
  async function handleRetry() {
    if (!product) return;
    setFailedJob(null);
    setEmptyJob(null);
    setActiveJobId(null);
    setIndexationMode("indexing");
    await ensurePipelineRunning(slug, product);
  }

  async function handleSubscribeNotify() {
    const email = notifyEmail.trim();
    if (!email) {
      setNotifyError("Please enter your email.");
      setNotifyStatus("error");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setNotifyError("Please enter a valid email address.");
      setNotifyStatus("error");
      return;
    }

    setNotifyStatus("submitting");
    setNotifyError(null);
    try {
      const res = await fetch(`/api/products/${slug}/indexation-notify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(body || "Failed to subscribe.");
      }
      setNotifyStatus("success");
    } catch (err) {
      setNotifyStatus("error");
      setNotifyError(
        err instanceof Error ? err.message : "Failed to subscribe.",
      );
    }
  }

  if (loading || (!data && indexationMode === "unknown")) {
    return (
      <div className="space-y-8">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <div className="space-y-2">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-32" />
          </div>
        </div>
        <Skeleton className="h-64 w-full rounded-3xl" />
        <div className="grid gap-6 md:grid-cols-2">
          <Skeleton className="h-48 rounded-2xl" />
          <Skeleton className="h-48 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (!data) {
    // If product exists but indexation isn't ready, show the indexation message + email capture
    if (product && indexationMode === "indexing") {
      // Terminal outcomes that must NOT retrigger the pipeline:
      //   - emptyJob  (no_documents): crawl finished, found nothing. No retry —
      //                a re-run yields the same result.
      //   - failedJob (failed):       interrupted/errored. Offer a manual Retry.
      const terminalJob = emptyJob ?? failedJob;
      const isEmpty = emptyJob !== null;
      const isFailed = failedJob !== null;
      // The crawl succeeded (documents were stored) but a later stage — document
      // analysis or overview synthesis — failed. Don't blame the crawl in this case.
      const isAnalysisFailure = isFailed && (failedJob?.documents_stored ?? 0) > 0;
      const crawlErrors = terminalJob?.crawl_errors ?? [];
      const allRobotsBlocked =
        crawlErrors.length > 0 &&
        crawlErrors.every((e) => e.error_type === "robots_txt_blocked");

      return (
        <div className="space-y-6">
          <div className="border-b border-border pb-8">
            <h1 className="text-4xl md:text-5xl font-display font-medium tracking-tight text-foreground">
              {product.name}
            </h1>
            <p className="text-muted-foreground mt-4 max-w-2xl text-sm leading-relaxed">
              {isEmpty
                ? "We could not find any policy documents to analyze for this company."
                : isAnalysisFailure
                  ? "We found this company's policy documents but couldn't complete the analysis. This is usually temporary — please try again."
                  : isFailed
                    ? "We were unable to crawl this company's policy documents."
                    : "Indexation is in progress for this company. Our systems are currently mapping the privacy landscape. Please return shortly once the analysis is complete."}
            </p>
          </div>

          {/* Terminal outcome details (no documents found, or a failure) */}
          {terminalJob && (
            <div className="border border-border bg-background">
              <div className="p-6 border-b border-border bg-muted/5">
                <div className="flex items-center gap-3">
                  <ShieldBan
                    className="h-5 w-5 text-amber-600"
                    strokeWidth={1.5}
                  />
                  <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                    {isEmpty
                      ? "No Documents Found"
                      : isAnalysisFailure
                        ? "Analysis Failed"
                        : "Crawl Failed"}
                  </h3>
                </div>
              </div>
              <div className="p-6 space-y-4">
                {allRobotsBlocked ? (
                  <div className="space-y-3">
                    <h2 className="text-xl font-display font-medium text-foreground">
                      Blocked by robots.txt
                    </h2>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      This website restricts automated access via its robots.txt
                      file. Our crawler was unable to fetch any policy
                      documents. You may need to review their policies manually
                      on their website.
                    </p>
                    <div className="space-y-2 pt-2">
                      {crawlErrors.map((err) => (
                        <div
                          key={err.url}
                          className="flex items-start gap-2 text-xs text-muted-foreground"
                        >
                          <ShieldBan className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                          <a
                            href={err.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-[11px] underline decoration-muted-foreground/30 hover:decoration-foreground break-all"
                          >
                            {err.url}
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <h2 className="text-xl font-display font-medium text-foreground">
                      {isEmpty
                        ? "No policy documents found on this site"
                        : isAnalysisFailure
                          ? "We found documents but couldn't analyze them"
                          : "Unable to crawl policy documents"}
                    </h2>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {terminalJob.error ??
                        (crawlErrors.length > 0
                          ? `${crawlErrors.length} URL(s) failed during crawling.`
                          : "We could not retrieve any policy documents from this site.")}
                    </p>
                    {crawlErrors.length > 0 && (
                      <div className="space-y-2 pt-2">
                        {crawlErrors.slice(0, 5).map((err) => (
                          <div
                            key={err.url}
                            className="flex items-start gap-2 text-xs text-muted-foreground"
                          >
                            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-destructive" />
                            <div>
                              <span className="font-mono text-[11px] break-all">
                                {err.url}
                              </span>
                              <span className="ml-1.5 text-destructive/70">
                                {err.error_message ?? err.error_type}
                              </span>
                            </div>
                          </div>
                        ))}
                        {crawlErrors.length > 5 && (
                          <p className="text-xs text-muted-foreground pl-4">
                            ...and {crawlErrors.length - 5} more
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Manual retry — available for any terminal non-success outcome.
                    Even when no documents were found and no error occurred, the
                    crawler may have improved since, so allow another attempt. */}
                <div className="pt-2">
                  <Button
                    onClick={handleRetry}
                    className="h-11 px-6 bg-foreground text-background hover:bg-foreground/90 rounded-none text-[10px] uppercase tracking-[0.2em] font-bold"
                  >
                    <RotateCcw className="mr-2 h-3.5 w-3.5" />
                    Try again
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Notification + pipeline progress (only while in progress / fresh) */}
          {!terminalJob && (
            <div className="border border-border bg-background">
              <div className="p-6 border-b border-border bg-muted/5">
                <div className="flex items-center gap-3">
                  <Shield
                    className="h-5 w-5 text-foreground"
                    strokeWidth={1.5}
                  />
                  <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                    Notification Service
                  </h3>
                </div>
              </div>
              <div className="p-6 space-y-6">
                <div className="space-y-2">
                  <h2 className="text-xl font-display font-medium text-foreground">
                    Get notified when analysis completes
                  </h2>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">
                    Secure your update by subscribing below
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row gap-4">
                  <Input
                    value={notifyEmail}
                    onChange={(e) => {
                      setNotifyEmail(e.target.value);
                      if (notifyStatus !== "idle") setNotifyStatus("idle");
                      if (notifyError) setNotifyError(null);
                    }}
                    placeholder="example@email.com"
                    className="h-12 border-border bg-transparent rounded-none"
                    type="email"
                    autoComplete="email"
                  />
                  <Button
                    onClick={handleSubscribeNotify}
                    disabled={notifyStatus === "submitting"}
                    className="h-12 px-8 bg-foreground text-background hover:bg-foreground/90 rounded-none text-[10px] uppercase tracking-[0.2em] font-bold"
                  >
                    {notifyStatus === "submitting"
                      ? "Processing..."
                      : "Subscribe"}
                  </Button>
                </div>

                {notifyStatus === "success" && (
                  <div className="p-4 border border-[#2B7A5C]/20 bg-[#2B7A5C]/5 text-[#2B7A5C] text-[10px] uppercase tracking-widest font-bold">
                    Subscription active. We will notify you upon completion.
                  </div>
                )}
                {notifyStatus === "error" && notifyError && (
                  <div className="p-4 border border-[#BD452D]/20 bg-[#BD452D]/5 text-[#BD452D] text-[10px] uppercase tracking-widest font-bold">
                    {notifyError}
                  </div>
                )}

                {activeJobId && (
                  <div className="pt-6 border-t border-border">
                    <div className="mb-4 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
                      Analysis Pipeline Status
                    </div>
                    <PipelineProgress jobId={activeJobId} />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      );
    }

    return (
      <ErrorDisplay
        variant="not-found"
        title="Product Not Found"
        message="The product you're looking for doesn't exist or has been removed."
        actionLabel="Browse Products"
        actionHref="/products"
      />
    );
  }

  const formattedDate = data.last_updated
    ? new Date(data.last_updated).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between border-b border-border pb-8">
        <div className="flex items-start gap-4">
          <Link href="/products">
            <Button
              variant="outline"
              size="icon"
              className="h-10 w-10 shrink-0 border-border bg-transparent hover:bg-muted/5 transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-4xl md:text-5xl font-display font-medium tracking-tight text-foreground">
              {data.product_name}
            </h1>
            <div className="flex flex-wrap items-center gap-4 mt-3">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-muted-foreground whitespace-nowrap">
                Policy overview
              </span>
              <div className="h-px w-8 bg-border hidden sm:block" />
              {formattedDate && (
                <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  Last Updated {formattedDate}
                </span>
              )}
            </div>
            <p className="mt-4 max-w-2xl text-sm text-muted-foreground leading-relaxed">
              Generated after we crawl and analyze this product&apos;s published
              policy documents (privacy, terms, cookies, and related notices).
              For a quick read on data use, risks, and what you may be agreeing
              to. Not legal advice.
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        defaultValue="overview"
        className="space-y-12"
        onValueChange={(value) => {
          posthog.capture("product_tab_changed", {
            tab_name: value,
            product_slug: slug,
            product_name: data.product_name,
          });
        }}
      >
        <div>
          <TabsList
            variant="underline"
            className="w-full sm:w-auto gap-8"
          >
            <TabsTrigger
              value="overview"
              variant="underline"
              className="px-0 text-[10px] uppercase tracking-[0.2em] font-bold"
            >
              Overview
            </TabsTrigger>
            <TabsTrigger
              value="sources"
              variant="underline"
              className="px-0 text-[10px] uppercase tracking-[0.2em] font-bold gap-2"
            >
              Sources
              {documents.length > 0 && (
                <span className="px-1.5 py-0.5 border border-border text-[8px] font-bold">
                  {documents.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="space-y-6 mt-0">
          {/* PRIMARY: Consumer TOS-explainer — the free-funnel hero */}
          {explainer && (
            <>
              <ConsumerExplainerView explainer={explainer} />

              {/* Divider into the secondary, detailed policy overview */}
              <div className="flex items-center gap-4 pt-8 pb-2">
                <div className="h-px flex-1 bg-border" />
                <span className="text-[10px] uppercase tracking-[0.3em] font-medium text-muted-foreground whitespace-nowrap">
                  Full Policy Overview
                </span>
                <div className="h-px flex-1 bg-border" />
              </div>
            </>
          )}

          {/* Verdict Hero */}
          <VerdictHero
            productName={data.product_name}
            companyName={data.company_name}
            verdict={data.verdict}
            riskScore={data.risk_score}
            summary={data.one_line_summary}
            keypoints={data.keypoints}
          />

          {/* Privacy Signals - Quick facts right after verdict */}
          {data.privacy_signals && (
            <PrivacySignals signals={data.privacy_signals} />
          )}

          {/* Coverage */}
          {data.coverage && data.coverage.length > 0 && (
            <div className="border border-border bg-background">
              <div className="p-6 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <LayoutDashboard
                    className="h-5 w-5 text-foreground"
                    strokeWidth={1.5}
                  />
                  <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                    Policy Coverage
                  </h3>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4">
                {data.coverage.map((item, idx) => {
                  const coverageStyles: Record<
                    CoverageItem["status"],
                    { className: string; label: string }
                  > = {
                    found: {
                      className:
                        "border-[#2B7A5C]/20 bg-[#2B7A5C]/5 text-[#2B7A5C]",
                      label: "Found",
                    },
                    ambiguous: {
                      className:
                        "border-[#B58D2D]/20 bg-[#B58D2D]/5 text-[#B58D2D]",
                      label: "Ambiguous",
                    },
                    missing: {
                      className:
                        "border-[#BD452D]/20 bg-[#BD452D]/5 text-[#BD452D]",
                      label: "Missing",
                    },
                    not_analyzed: {
                      className: "border-border bg-muted/5 text-muted-foreground",
                      label: "Not Analyzed",
                    },
                  };
                  const coverage = coverageStyles[item.status];
                  return (
                    <div
                      key={`${item.category}-${item.status}`}
                      className={cn(
                        "p-6 flex flex-col gap-4 bg-background border-b border-border",
                        idx % 4 !== 3 ? "md:border-r border-border" : "",
                      )}
                    >
                      <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground capitalize">
                        {item.category.replace(/_/g, " ")}
                      </span>
                      <div
                        className={cn(
                          "px-2 py-0.5 text-[8px] font-bold uppercase tracking-tighter border w-fit",
                          coverage.className,
                        )}
                      >
                        {coverage.label}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Score Breakdown - Why the score is what it is */}
          {data.detailed_scores && (
            <ScoreBreakdown
              detailedScores={data.detailed_scores}
              riskScore={data.risk_score}
            />
          )}

          {/* Data Story */}
          <DataStory
            dataCollectionDetails={data.data_collection_details}
            dataCollected={data.data_collected}
            dataPurposes={data.data_purposes}
          />

          {/* Sharing Map */}
          <SharingMap
            thirdPartyDetails={data.third_party_details}
            thirdPartySharing={data.third_party_sharing}
          />

          {/* Your Power */}
          <YourPower
            rights={data.your_rights}
            dangers={data.dangers}
            benefits={data.benefits}
          />

          {/* Contract Highlights */}
          {data.contract_clauses && data.contract_clauses.length > 0 && (
            <div className="border border-border bg-background">
              <div className="p-6 border-b border-border">
                <div className="flex items-center gap-3">
                  <FileText
                    className="h-5 w-5 text-foreground"
                    strokeWidth={1.5}
                  />
                  <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                    Contract Highlights
                  </h3>
                </div>
              </div>
              <div className="divide-y divide-border">
                {data.contract_clauses.map((clause, idx) => (
                  <div
                    key={idx}
                    className="p-6 flex items-start gap-4 hover:bg-muted/5 transition-colors"
                  >
                    <div className="mt-1.5 h-1.5 w-1.5 border border-border bg-foreground shrink-0" />
                    <p className="text-sm text-foreground/80 leading-relaxed italic font-serif">
                      &ldquo;{clause}&rdquo;
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Compliance Badges */}
          {((data.compliance && Object.keys(data.compliance).length > 0) ||
            (data.compliance_status &&
              Object.keys(data.compliance_status).length > 0)) && (
            <ComplianceBadges
              compliance={data.compliance}
              complianceStatus={data.compliance_status}
            />
          )}
        </TabsContent>

        <TabsContent value="sources" className="mt-0">
          {documentsLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-12 w-64 rounded-xl" />
              <Skeleton className="h-32 rounded-2xl" />
              <Skeleton className="h-32 rounded-2xl" />
              <Skeleton className="h-32 rounded-2xl" />
            </div>
          ) : (
            <SourcesList productSlug={slug} documents={documents} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
