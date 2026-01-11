"use client";

import { ArrowLeft, Calendar, FileText, LayoutDashboard } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useParams } from "next/navigation";
import posthog from "posthog-js";

import { useEffect, useRef, useState } from "react";

import { DataStory } from "@/components/dashboard/overview/data-story";
import { SharingMap } from "@/components/dashboard/overview/sharing-map";
import { VerdictHero } from "@/components/dashboard/overview/verdict-hero";
import { YourPower } from "@/components/dashboard/overview/your-power";
import { SourcesList } from "@/components/dashboard/sources-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorDisplay } from "@/components/ui/error-display";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

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
    <div className="space-y-8">
      {/* Risk Prioritization */}
      {deepAnalysis.risk_prioritization && (
        <Card variant="elevated">
          <CardContent className="p-6">
            <h2 className="text-xl font-semibold font-display mb-4">
              Risk Prioritization
            </h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {deepAnalysis.risk_prioritization.critical?.length > 0 && (
                <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20">
                  <h3 className="font-medium text-red-600 dark:text-red-400 mb-2">
                    Critical
                  </h3>
                  <ul className="space-y-1 text-sm">
                    {deepAnalysis.risk_prioritization.critical.map(
                      (risk: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-1.5 shrink-0" />
                          {risk}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              )}
              {deepAnalysis.risk_prioritization.high?.length > 0 && (
                <div className="p-4 rounded-xl bg-orange-500/10 border border-orange-500/20">
                  <h3 className="font-medium text-orange-600 dark:text-orange-400 mb-2">
                    High
                  </h3>
                  <ul className="space-y-1 text-sm">
                    {deepAnalysis.risk_prioritization.high.map(
                      (risk: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-orange-500 mt-1.5 shrink-0" />
                          {risk}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              )}
              {deepAnalysis.risk_prioritization.medium?.length > 0 && (
                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
                  <h3 className="font-medium text-amber-600 dark:text-amber-400 mb-2">
                    Medium
                  </h3>
                  <ul className="space-y-1 text-sm">
                    {deepAnalysis.risk_prioritization.medium.map(
                      (risk: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                          {risk}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              )}
              {deepAnalysis.risk_prioritization.low?.length > 0 && (
                <div className="p-4 rounded-xl bg-green-500/10 border border-green-500/20">
                  <h3 className="font-medium text-green-600 dark:text-green-400 mb-2">
                    Low
                  </h3>
                  <ul className="space-y-1 text-sm">
                    {deepAnalysis.risk_prioritization.low.map(
                      (risk: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500 mt-1.5 shrink-0" />
                          {risk}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Enhanced Compliance */}
      {deepAnalysis.enhanced_compliance &&
        Object.keys(deepAnalysis.enhanced_compliance).length > 0 && (
          <Card variant="elevated">
            <CardContent className="p-6">
              <h2 className="text-xl font-semibold font-display mb-4">
                Compliance Analysis
              </h2>
              <div className="grid gap-4 md:grid-cols-2">
                {Object.entries(deepAnalysis.enhanced_compliance).map(
                  ([reg, comp]: [string, any]) => (
                    <div
                      key={reg}
                      className="p-4 rounded-xl border border-border/50 bg-muted/30"
                    >
                      <h3 className="font-semibold mb-2">{reg}</h3>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Status</span>
                          <span className="font-medium">{comp.status}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Score</span>
                          <span className="font-medium">{comp.score}/10</span>
                        </div>
                        {comp.violations?.length > 0 && (
                          <div className="pt-2 border-t border-border/50">
                            <span className="text-muted-foreground">
                              Violations:
                            </span>
                            <ul className="mt-1 space-y-1">
                              {comp.violations.map((v: any, i: number) => (
                                <li
                                  key={i}
                                  className="text-red-600 dark:text-red-400"
                                >
                                  {v.requirement}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  ),
                )}
              </div>
            </CardContent>
          </Card>
        )}
    </div>
  );
}

export default function CompanyPage() {
  const params = useParams();
  const slug = params.slug as string;
  const [data, setData] = useState<ProductOverview | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch(`/api/products/${slug}/overview`);
        if (res.ok) {
          const json = await res.json();
          setData(json);
        } else {
          console.error("Failed to fetch product overview:", res.statusText);
        }
      } catch (error) {
        console.error("Failed to fetch product data", error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [slug]);

  useEffect(() => {
    async function fetchDocuments() {
      setDocumentsLoading(true);
      try {
        const res = await fetch(`/api/products/${slug}/documents`);
        if (res.ok) {
          const json = await res.json();
          setDocuments(json);
        } else {
          console.error("Failed to fetch product documents:", res.statusText);
        }
      } catch (error) {
        console.error("Failed to fetch product documents", error);
      } finally {
        setDocumentsLoading(false);
      }
    }
    fetchDocuments();
  }, [slug]);

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
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between"
      >
        <div className="flex items-start gap-4">
          <Link href="/products">
            <Button
              variant="ghost"
              size="icon"
              className="rounded-xl h-10 w-10 shrink-0 hover:bg-muted"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl md:text-4xl font-bold font-display tracking-tight text-foreground">
              {data.product_name}
            </h1>
            <div className="flex flex-wrap items-center gap-3 mt-2">
              <Badge variant="outline" className="gap-1.5">
                Privacy Analysis
              </Badge>
              {formattedDate && (
                <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  Updated {formattedDate}
                </span>
              )}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Tabs */}
      <Tabs
        defaultValue="overview"
        className="space-y-8"
        onValueChange={(value) => {
          posthog.capture("product_tab_changed", {
            tab_name: value,
            product_slug: slug,
            product_name: data.product_name,
          });
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <TabsList variant="pills" className="w-full sm:w-auto">
            <TabsTrigger value="overview" variant="pills" className="gap-2">
              <LayoutDashboard className="h-4 w-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="sources" variant="pills" className="gap-2">
              <FileText className="h-4 w-4" />
              Sources
              {documents.length > 0 && (
                <Badge variant="secondary" size="sm" className="ml-1">
                  {documents.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>
        </motion.div>

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
