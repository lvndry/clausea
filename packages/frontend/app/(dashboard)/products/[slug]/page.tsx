"use client";

import {
  ArrowLeft,
  Calendar,
  FileText,
  LayoutDashboard,
  Shield,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useParams } from "next/navigation";
import posthog from "posthog-js";

import { useEffect, useRef, useState } from "react";

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

interface ProductOverview {
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
  privacy_signals?: PrivacySignalsData | null;
  coverage?: CoverageItem[] | null;
  contract_clauses?: string[] | null;
}

interface DocumentSummary {
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

function DeepAnalysisTab({ slug }: { slug: string }) {
  const [loading, setLoading] = useState(true);
  const [deepAnalysis, setDeepAnalysis] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchDeepAnalysis() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/products/${slug}/deep-analysis`);
        if (res.ok) {
          const json = await res.json();
          setDeepAnalysis(json);
        } else {
          setError("Failed to fetch deep analysis");
        }
      } catch (err) {
        console.error("Failed to fetch deep analysis", err);
        setError("Failed to fetch deep analysis");
      } finally {
        setLoading(false);
      }
    }
    fetchDeepAnalysis();
  }, [slug]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  if (error || !deepAnalysis) {
    return (
      <ErrorDisplay
        variant="error"
        title="Analysis Unavailable"
        message={error || "Deep analysis is not available for this product."}
      />
    );
  }

  return (
    <div className="space-y-12">
      {/* Risk Prioritization */}
      {deepAnalysis.risk_prioritization && (
        <div className="border border-border bg-background">
          <div className="p-6 border-b border-border">
            <div className="flex items-center gap-3">
              <LayoutDashboard
                className="h-5 w-5 text-foreground"
                strokeWidth={1.5}
              />
              <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                Risk Prioritization
              </h3>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 divide-x divide-border">
            {/* Critical */}
            <div className="p-6 space-y-4">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[#BD452D]">
                Critical
              </span>
              <ul className="space-y-3">
                {deepAnalysis.risk_prioritization.critical?.map(
                  (risk: string, i: number) => (
                    <li
                      key={i}
                      className="text-sm text-foreground leading-relaxed flex items-start gap-3"
                    >
                      <div className="mt-1.5 h-1 w-1 bg-[#BD452D] shrink-0" />
                      {risk}
                    </li>
                  ),
                )}
              </ul>
            </div>
            {/* High */}
            <div className="p-6 space-y-4 border-t md:border-t-0">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[#BD452D]">
                High
              </span>
              <ul className="space-y-3">
                {deepAnalysis.risk_prioritization.high?.map(
                  (risk: string, i: number) => (
                    <li
                      key={i}
                      className="text-sm text-foreground leading-relaxed flex items-start gap-3"
                    >
                      <div className="mt-1.5 h-1 w-1 bg-[#BD452D] shrink-0 opacity-60" />
                      {risk}
                    </li>
                  ),
                )}
              </ul>
            </div>
            {/* Medium */}
            <div className="p-6 space-y-4 border-t lg:border-t-0">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[#B58D2D]">
                Medium
              </span>
              <ul className="space-y-3">
                {deepAnalysis.risk_prioritization.medium?.map(
                  (risk: string, i: number) => (
                    <li
                      key={i}
                      className="text-sm text-foreground leading-relaxed flex items-start gap-3"
                    >
                      <div className="mt-1.5 h-1 w-1 bg-[#B58D2D] shrink-0" />
                      {risk}
                    </li>
                  ),
                )}
              </ul>
            </div>
            {/* Low */}
            <div className="p-6 space-y-4 border-t lg:border-t-0">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[#2B7A5C]">
                Low Risk
              </span>
              <ul className="space-y-3">
                {deepAnalysis.risk_prioritization.low?.map(
                  (risk: string, i: number) => (
                    <li
                      key={i}
                      className="text-sm text-foreground leading-relaxed flex items-start gap-3"
                    >
                      <div className="mt-1.5 h-1 w-1 bg-[#2B7A5C] shrink-0" />
                      {risk}
                    </li>
                  ),
                )}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Enhanced Compliance */}
      {deepAnalysis.enhanced_compliance &&
        Object.keys(deepAnalysis.enhanced_compliance).length > 0 && (
          <div className="border border-border bg-background">
            <div className="p-6 border-b border-border">
              <div className="flex items-center gap-3">
                <Shield className="h-5 w-5 text-foreground" strokeWidth={1.5} />
                <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
                  Regulatory Compliance Analysis
                </h3>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 divide-x divide-border">
              {Object.entries(deepAnalysis.enhanced_compliance).map(
                ([reg, comp]: [string, any]) => (
                  <div key={reg} className="p-6 space-y-6">
                    <div className="flex justify-between items-start">
                      <h4 className="font-display font-medium text-xl text-foreground">
                        {reg}
                      </h4>
                      <div
                        className={cn(
                          "px-3 py-1 border text-[10px] font-bold uppercase tracking-widest",
                          comp.score >= 7
                            ? "border-[#2B7A5C]/20 bg-[#2B7A5C]/5 text-[#2B7A5C]"
                            : comp.score >= 4
                              ? "border-[#B58D2D]/20 bg-[#B58D2D]/5 text-[#B58D2D]"
                              : "border-[#BD452D]/20 bg-[#BD452D]/5 text-[#BD452D]",
                        )}
                      >
                        {comp.status}
                      </div>
                    </div>

                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl font-display font-medium text-foreground">
                        {comp.score}
                      </span>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground leading-none">
                        / 10 Score
                      </span>
                    </div>

                    {comp.violations?.length > 0 && (
                      <div className="pt-6 border-t border-border space-y-4">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-[#BD452D]">
                          Detected Deviations
                        </span>
                        <ul className="space-y-3">
                          {comp.violations.map((v: any, i: number) => (
                            <li
                              key={i}
                              className="text-sm text-[#BD452D] italic flex items-start gap-3"
                            >
                              <span className="mt-1.5 h-1.5 w-1.5 bg-[#BD452D] shrink-0" />
                              {v.requirement}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ),
              )}
            </div>
          </div>
        )}
    </div>
  );
}

export default function CompanyPage() {
  const params = useParams();
  const slug = params.slug as string;
  const [product, setProduct] = useState<Product | null>(null);
  const [data, setData] = useState<ProductOverview | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [indexationMode, setIndexationMode] = useState<
    "ready" | "indexing" | "unknown"
  >("unknown");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [notifyEmail, setNotifyEmail] = useState("");
  const [notifyStatus, setNotifyStatus] = useState<
    "idle" | "submitting" | "success" | "error"
  >("idle");
  const [notifyError, setNotifyError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        // Fetch the base product first so we can trigger indexation if needed
        const prodRes = await fetch(`/api/products/${slug}`);
        if (!prodRes.ok) {
          setProduct(null);
          setData(null);
          setIndexationMode("ready"); // render not-found
          return;
        }
        const prodJson = (await prodRes.json()) as Product;
        setProduct(prodJson);

        // Fetch documents next; if none, auto-trigger pipeline and show "indexing" UI
        setDocumentsLoading(true);
        const docsRes = await fetch(`/api/products/${slug}/documents`);
        const docsJson = docsRes.ok
          ? ((await docsRes.json()) as DocumentSummary[])
          : [];
        setDocuments(docsJson);
        setDocumentsLoading(false);

        if (!docsJson.length) {
          await ensurePipelineRunning(slug, prodJson);
          setIndexationMode("indexing");
          setData(null);
          return;
        }

        // Documents exist; try to fetch overview (may generate on the fly)
        const res = await fetch(`/api/products/${slug}/overview`);
        if (res.ok) {
          const json = await res.json();
          setData(json);
          setIndexationMode("ready");
        } else {
          // If overview isn't available yet, treat as "indexing" and ensure pipeline is running.
          await ensurePipelineRunning(slug, prodJson);
          setIndexationMode("indexing");
          setData(null);
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

  if (loading) {
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
      return (
        <div className="space-y-6">
          <div className="border-b border-border pb-8">
            <h1 className="text-4xl md:text-5xl font-display font-medium tracking-tight text-foreground">
              {product.name}
            </h1>
            <p className="text-muted-foreground mt-4 max-w-2xl text-sm leading-relaxed">
              Indexation is in progress for this company. Our systems are
              currently mapping the privacy landscape. Please return shortly
              once the analysis is complete.
            </p>
          </div>

          <div className="border border-border bg-background">
            <div className="p-6 border-b border-border bg-muted/5">
              <div className="flex items-center gap-3">
                <Shield className="h-5 w-5 text-foreground" strokeWidth={1.5} />
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
                Privacy Analysis
              </span>
              <div className="h-px w-8 bg-border hidden sm:block" />
              {formattedDate && (
                <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-medium text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  Last Updated {formattedDate}
                </span>
              )}
            </div>
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
          <TabsList className="w-full sm:w-auto h-auto p-0 bg-transparent border-b border-border gap-8">
            <TabsTrigger
              value="overview"
              className="px-0 py-4 text-[10px] uppercase tracking-[0.2em] font-bold data-[state=active]:border-b-2 data-[state=active]:border-foreground data-[state=active]:bg-transparent rounded-none transition-all"
            >
              Overview
            </TabsTrigger>
            <TabsTrigger
              value="sources"
              className="px-0 py-4 text-[10px] uppercase tracking-[0.2em] font-bold data-[state=active]:border-b-2 data-[state=active]:border-foreground data-[state=active]:bg-transparent rounded-none transition-all gap-2"
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
                {data.coverage.map((item, idx) => (
                  <div
                    key={`${item.category}-${item.status}`}
                    className={cn(
                      "p-6 flex flex-col gap-4 bg-background border-b border-border",
                      idx % 4 !== 3 ? "md:border-r border-border" : "",
                    )}
                  >
                    <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
                      {item.category.replace(/_/g, " ")}
                    </span>
                    <div
                      className={cn(
                        "px-2 py-0.5 text-[8px] font-bold tracking-tighter border w-fit capitalize",
                        item.status === "found"
                          ? "border-[#2B7A5C]/20 bg-[#2B7A5C]/5 text-[#2B7A5C]"
                          : item.status === "ambiguous"
                            ? "border-[#B58D2D]/20 bg-[#B58D2D]/5 text-[#B58D2D]"
                            : "border-border bg-muted/5 text-muted-foreground",
                      )}
                    >
                      {item.status}
                    </div>
                  </div>
                ))}
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
          {data.compliance_status &&
            Object.keys(data.compliance_status).length > 0 && (
              <ComplianceBadges complianceStatus={data.compliance_status} />
            )}
        </TabsContent>

        <TabsContent value="analysis" className="mt-0">
          <DeepAnalysisTab slug={slug} />
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
