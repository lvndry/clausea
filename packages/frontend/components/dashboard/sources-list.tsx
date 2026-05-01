"use client";

import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  FolderOpen,
  Link as LinkIcon,
  ShieldAlert,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import posthog from "posthog-js";

import { useState } from "react";

import { MarkdownRenderer } from "@/components/markdown/markdown-renderer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { getVerdictConfig } from "@/lib/verdict";

interface EvidenceSpan {
  document_id: string;
  url: string;
  content_hash?: string | null;
  quote: string;
  start_char?: number | null;
  end_char?: number | null;
  section_title?: string | null;
}

interface KeypointWithEvidence {
  keypoint: string;
  evidence: EvidenceSpan[];
}

interface ExtractedItem {
  value: string;
  evidence: EvidenceSpan[];
}

interface DocumentExtraction {
  data_collected: ExtractedItem[];
  data_purposes: ExtractedItem[];
  retention_policies: ExtractedItem[];
  third_party_details: ExtractedItem[];
  user_rights: ExtractedItem[];
  ai_usage: ExtractedItem[];
  international_transfers: ExtractedItem[];
  government_access: ExtractedItem[];
  consent_mechanisms: ExtractedItem[];
  dangers: ExtractedItem[];
  benefits: ExtractedItem[];
}

interface CriticalClause {
  clause_type: string;
  section_title?: string | null;
  quote: string;
  risk_level: "low" | "medium" | "high" | "critical";
  plain_english: string;
  why_notable: string;
  analysis: string;
  compliance_impact: string[];
}

interface DocumentRiskBreakdown {
  overall_risk: number;
  risk_by_category: Record<string, number>;
  top_concerns: string[];
  positive_protections: string[];
  missing_information: string[];
}

interface DocumentSection {
  section_title: string;
  content: string;
  importance: "low" | "medium" | "high" | "critical";
  analysis: string;
  related_clauses: string[];
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
  keypoints_with_evidence?: KeypointWithEvidence[] | null;
  critical_clauses?: CriticalClause[] | null;
  document_risk_breakdown?: DocumentRiskBreakdown | null;
  key_sections?: DocumentSection[] | null;
}

interface SourcesListProps {
  productSlug: string;
  documents: DocumentSummary[];
}

function normalizeForMatch(s: string): string {
  return (s || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function deriveEvidenceForKeypoint(
  keypoint: string,
  extraction: DocumentExtraction,
): EvidenceSpan[] {
  const kp = normalizeForMatch(keypoint);
  if (!kp) return [];

  const found: EvidenceSpan[] = [];

  for (const key of [
    "data_collected",
    "data_purposes",
    "retention_policies",
    "user_rights",
    "third_party_details",
    "ai_usage",
    "international_transfers",
    "government_access",
    "consent_mechanisms",
    "dangers",
    "benefits",
  ] as const) {
    for (const item of extraction[key] || []) {
      const value = normalizeForMatch(item.value);
      if (value && kp.includes(value) && item.evidence?.length) {
        found.push(...item.evidence);
        if (found.length >= 3) return found.slice(0, 3);
      }
    }
  }

  return found.slice(0, 3);
}

const RISK_LEVEL_CONFIG = {
  critical: {
    label: "Critical",
    className: "bg-red-100 dark:bg-red-950/40 border-red-200 dark:border-red-900",
    badgeVariant: "danger" as const,
    icon: ShieldAlert,
    iconClass: "text-red-500",
  },
  high: {
    label: "High",
    className: "bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-900",
    badgeVariant: "warning" as const,
    icon: AlertTriangle,
    iconClass: "text-orange-500",
  },
  medium: {
    label: "Medium",
    className: "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-900",
    badgeVariant: "warning" as const,
    icon: AlertTriangle,
    iconClass: "text-yellow-600",
  },
  low: {
    label: "Low",
    className: "bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900",
    badgeVariant: "success" as const,
    icon: CheckCircle,
    iconClass: "text-emerald-500",
  },
};

export function SourcesList({ productSlug, documents }: SourcesListProps) {
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set());
  const [expandedKeypoints, setExpandedKeypoints] = useState<
    Record<string, Set<number>>
  >({});
  const [extractions, setExtractions] = useState<
    Record<string, DocumentExtraction>
  >({});
  const [extractionLoading, setExtractionLoading] = useState<
    Record<string, boolean>
  >({});
  function toggleExpanded(docId: string, docTitle?: string | null) {
    const newExpanded = new Set(expandedDocs);
    const isExpanding = !newExpanded.has(docId);
    if (newExpanded.has(docId)) {
      newExpanded.delete(docId);
    } else {
      newExpanded.add(docId);
    }
    setExpandedDocs(newExpanded);

    if (isExpanding) {
      posthog.capture("document_source_clicked", {
        document_id: docId,
        document_title: docTitle || "Untitled Document",
        product_slug: productSlug,
      });
    }
  }

  function toggleKeypoint(docId: string, idx: number) {
    setExpandedKeypoints((prev) => {
      const next = { ...prev };
      const current = next[docId] ? new Set(next[docId]) : new Set<number>();
      if (current.has(idx)) current.delete(idx);
      else current.add(idx);
      next[docId] = current;
      return next;
    });
  }

  async function ensureExtractionLoaded(docId: string) {
    if (extractions[docId] || extractionLoading[docId]) return;
    setExtractionLoading((s) => ({ ...s, [docId]: true }));
    try {
      const res = await fetch(
        `/api/products/${productSlug}/documents/${docId}/extraction`,
      );
      if (!res.ok) return;
      const json = (await res.json()) as DocumentExtraction;
      setExtractions((s) => ({ ...s, [docId]: json }));
    } catch {
      // ignore
    } finally {
      setExtractionLoading((s) => ({ ...s, [docId]: false }));
    }
  }

  function handleToggleExpanded(doc: DocumentSummary) {
    toggleExpanded(doc.id, doc.title);
  }

  if (documents.length === 0) {
    return (
      <Card variant="default" className="border-border">
        <CardContent className="py-12 text-center">
          <div className="w-14 h-14 rounded-lg bg-muted/50 flex items-center justify-center mx-auto mb-3">
            <FolderOpen className="h-7 w-7 text-muted-foreground/50" />
          </div>
          <h3 className="font-semibold text-base mb-1">No Source Documents</h3>
          <p className="text-muted-foreground text-sm max-w-sm mx-auto">
            No source documents are available for analysis yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card variant="default" className="border-border overflow-hidden">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
              <FileText className="h-5 w-5 text-violet-600 dark:text-violet-400" />
            </div>
            <div>
              <CardTitle className="text-lg">Source Documents</CardTitle>
              <p className="text-sm text-muted-foreground mt-0.5">
                Policy documents analyzed for this product
              </p>
            </div>
          </div>
          <Badge variant="outline" className="gap-1.5">
            <FileText className="h-3 w-3" />
            {documents.length}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-2.5">
        {documents.map((doc) => {
          const isExpanded = expandedDocs.has(doc.id);
          const verdictConfig = doc.verdict
            ? getVerdictConfig(doc.verdict)
            : null;
          const displaySummary = doc.summary;
          const displayKeypoints = doc.keypoints ?? [];
          const displayKeypointsWithEvidence = doc.keypoints_with_evidence;
          const displayCriticalClauses = doc.critical_clauses ?? [];
          const displayKeySections = doc.key_sections ?? [];
          const riskBreakdown = doc.document_risk_breakdown;

          const evidenceByKeypoint = new Map<string, EvidenceSpan[]>();
          const kpwe = displayKeypointsWithEvidence;
          if (kpwe && Array.isArray(kpwe)) {
            for (const entry of kpwe) {
              if (entry?.keypoint && entry.evidence?.length) {
                evidenceByKeypoint.set(
                  normalizeForMatch(entry.keypoint),
                  entry.evidence,
                );
              }
            }
          }

          return (
            <div
              key={doc.id}
              className={cn(
                "rounded-lg border overflow-hidden transition-all",
                isExpanded
                  ? "border-violet-300 dark:border-violet-700 bg-violet-50/50 dark:bg-violet-950/20"
                  : "border-border bg-card hover:border-violet-200 dark:hover:border-violet-800",
              )}
            >
              {/* Document Header */}
              <div
                className="p-4 cursor-pointer"
                onClick={() => handleToggleExpanded(doc)}
              >
                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div
                    className={cn(
                      "w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                      isExpanded
                        ? "bg-violet-100 dark:bg-violet-900/30"
                        : "bg-muted/50",
                    )}
                  >
                    <FileText
                      className={cn(
                        "h-4.5 w-4.5 transition-colors",
                        isExpanded
                          ? "text-violet-600 dark:text-violet-400"
                          : "text-muted-foreground",
                      )}
                    />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        {/* Title */}
                        <h4
                          className={cn(
                            "font-semibold text-sm mb-1 transition-colors",
                            isExpanded
                              ? "text-violet-700 dark:text-violet-300"
                              : "",
                          )}
                        >
                          {doc.title || "Untitled Document"}
                        </h4>

                        {/* URL */}
                        <a
                          href={doc.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-2"
                        >
                          <LinkIcon className="h-3 w-3" />
                          <span className="truncate max-w-[200px] sm:max-w-md">
                            {doc.url}
                          </span>
                          <ExternalLink className="h-3 w-3 opacity-50" />
                        </a>

                        {/* Badges */}
                        <div className="flex flex-wrap items-center gap-1.5">
                          {doc.doc_type && (
                            <Badge variant="outline" size="sm">
                              {doc.doc_type.replace(/_/g, " ")}
                            </Badge>
                          )}
                          {verdictConfig && (
                            <Badge
                              variant={verdictConfig.variant || "outline"}
                              size="sm"
                            >
                              {verdictConfig.label}
                            </Badge>
                          )}
                          {doc.risk_score !== null &&
                            doc.risk_score !== undefined && (
                              <Badge
                                variant={
                                  doc.risk_score >= 7
                                    ? "danger"
                                    : doc.risk_score >= 4
                                      ? "warning"
                                      : "success"
                                }
                                size="sm"
                              >
                                Risk: {doc.risk_score}/10
                              </Badge>
                            )}
                        </div>
                      </div>

                      {/* Expand button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleExpanded(doc);
                        }}
                        className={cn(
                          "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all shrink-0",
                          isExpanded
                            ? "bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300"
                            : "text-muted-foreground hover:bg-muted",
                        )}
                      >
                        {isExpanded ? (
                          <>
                            <ChevronDown className="h-3.5 w-3.5" />
                            Close
                          </>
                        ) : (
                          <>
                            <ChevronRight className="h-3.5 w-3.5" />
                            Details
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Expanded Content */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 pt-2 border-t border-violet-200 dark:border-violet-800">
                      {/* No analysis available */}
                      {!displaySummary &&
                        displayKeypoints.length === 0 &&
                        displayCriticalClauses.length === 0 &&
                        displayKeySections.length === 0 &&
                        !riskBreakdown && (
                          <p className="py-4 text-sm text-muted-foreground text-center">
                            No analysis available for this document yet.
                          </p>
                        )}

                      {(displaySummary ||
                        displayKeypoints.length > 0 ||
                        displayCriticalClauses.length > 0 ||
                        displayKeySections.length > 0 ||
                        !!riskBreakdown) && (
                        <div className="space-y-4">
                          {/* Summary */}
                          {displaySummary && (
                            <div className="text-sm text-foreground/90 leading-relaxed prose prose-sm dark:prose-invert max-w-none prose-p:my-2">
                              <MarkdownRenderer>
                                {displaySummary}
                              </MarkdownRenderer>
                            </div>
                          )}

                          {/* Risk breakdown */}
                          {riskBreakdown &&
                            (riskBreakdown.top_concerns?.length > 0 ||
                              riskBreakdown.positive_protections?.length >
                                0) && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                {riskBreakdown.top_concerns?.length > 0 && (
                                  <div className="rounded-md bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 p-3">
                                    <h6 className="text-[10px] font-bold uppercase tracking-widest text-red-700 dark:text-red-400 mb-2">
                                      Top Concerns
                                    </h6>
                                    <ul className="space-y-1">
                                      {riskBreakdown.top_concerns
                                        .slice(0, 4)
                                        .map((c, i) => (
                                          <li
                                            key={i}
                                            className="text-xs text-foreground/80 flex items-start gap-1.5"
                                          >
                                            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-red-400 shrink-0" />
                                            {c}
                                          </li>
                                        ))}
                                    </ul>
                                  </div>
                                )}
                                {riskBreakdown.positive_protections?.length >
                                  0 && (
                                  <div className="rounded-md bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900 p-3">
                                    <h6 className="text-[10px] font-bold uppercase tracking-widest text-emerald-700 dark:text-emerald-400 mb-2">
                                      Protections
                                    </h6>
                                    <ul className="space-y-1">
                                      {riskBreakdown.positive_protections
                                        .slice(0, 4)
                                        .map((p, i) => (
                                          <li
                                            key={i}
                                            className="text-xs text-foreground/80 flex items-start gap-1.5"
                                          >
                                            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                                            {p}
                                          </li>
                                        ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            )}

                          {/* Critical clauses */}
                          {displayCriticalClauses.length > 0 && (
                            <div>
                              <h5 className="text-[10px] font-bold text-violet-700 dark:text-violet-300 uppercase tracking-widest mb-2 flex items-center gap-2">
                                <span className="h-px w-4 bg-violet-300 dark:bg-violet-700" />
                                Critical Clauses
                              </h5>
                              <div className="space-y-2">
                                {displayCriticalClauses
                                  .slice(0, 5)
                                  .map((clause, i) => {
                                    const cfg =
                                      RISK_LEVEL_CONFIG[clause.risk_level] ||
                                      RISK_LEVEL_CONFIG.medium;
                                    const Icon = cfg.icon;
                                    return (
                                      <div
                                        key={i}
                                        className={cn(
                                          "rounded-md border p-3",
                                          cfg.className,
                                        )}
                                      >
                                        <div className="flex items-start gap-2 mb-1.5">
                                          <Icon
                                            className={cn(
                                              "h-3.5 w-3.5 mt-0.5 shrink-0",
                                              cfg.iconClass,
                                            )}
                                          />
                                          <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                                            <span className="text-xs font-semibold text-foreground/90">
                                              {clause.section_title ||
                                                clause.clause_type.replace(
                                                  /_/g,
                                                  " ",
                                                )}
                                            </span>
                                            <Badge
                                              variant={cfg.badgeVariant}
                                              size="sm"
                                            >
                                              {cfg.label}
                                            </Badge>
                                          </div>
                                        </div>
                                        {(clause.plain_english ||
                                          clause.analysis) && (
                                          <p className="text-xs text-foreground/80 leading-snug mb-2 ml-5">
                                            {clause.plain_english ||
                                              clause.analysis}
                                          </p>
                                        )}
                                        {clause.quote && (
                                          <blockquote className="text-xs leading-relaxed text-foreground/70 border-l-2 border-current/30 pl-2 ml-5 italic">
                                            &ldquo;{clause.quote}&rdquo;
                                          </blockquote>
                                        )}
                                      </div>
                                    );
                                  })}
                              </div>
                            </div>
                          )}

                          {/* Key sections */}
                          {displayKeySections.length > 0 && (
                            <div>
                              <h5 className="text-[10px] font-bold text-violet-700 dark:text-violet-300 uppercase tracking-widest mb-2 flex items-center gap-2">
                                <span className="h-px w-4 bg-violet-300 dark:bg-violet-700" />
                                Key Sections
                              </h5>
                              <div className="space-y-2">
                                {displayKeySections.slice(0, 5).map((section, i) => {
                                  const importanceColors = {
                                    critical: "border-red-200 dark:border-red-900 bg-red-50/50 dark:bg-red-950/20",
                                    high: "border-orange-200 dark:border-orange-900 bg-orange-50/50 dark:bg-orange-950/20",
                                    medium: "border-yellow-200 dark:border-yellow-900 bg-yellow-50/50 dark:bg-yellow-950/20",
                                    low: "border-border bg-card/50",
                                  };
                                  const importanceDotColors = {
                                    critical: "bg-red-400",
                                    high: "bg-orange-400",
                                    medium: "bg-yellow-400",
                                    low: "bg-muted-foreground",
                                  };
                                  return (
                                    <div
                                      key={i}
                                      className={cn(
                                        "rounded-md border p-3",
                                        importanceColors[section.importance] ?? importanceColors.low,
                                      )}
                                    >
                                      <div className="flex items-center gap-2 mb-1.5">
                                        <span className={cn("h-2 w-2 rounded-full shrink-0", importanceDotColors[section.importance] ?? importanceDotColors.low)} />
                                        <span className="text-xs font-semibold text-foreground/90">
                                          {section.section_title}
                                        </span>
                                      </div>
                                      {section.analysis && (
                                        <p className="text-xs text-foreground/80 leading-snug mb-2 ml-4">
                                          {section.analysis}
                                        </p>
                                      )}
                                      {section.content && (
                                        <blockquote className="text-xs leading-relaxed text-foreground/70 border-l-2 border-current/30 pl-2 ml-4 italic">
                                          &ldquo;{section.content}&rdquo;
                                        </blockquote>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Keypoints */}
                          {displayKeypoints.length > 0 && (
                            <div className="pt-1">
                              <h5 className="text-[10px] font-bold text-violet-700 dark:text-violet-300 uppercase tracking-widest mb-2 flex items-center gap-2">
                                <span className="h-px w-4 bg-violet-300 dark:bg-violet-700" />
                                Key Insights
                              </h5>
                              <div className="space-y-1.5">
                                {displayKeypoints.map(
                                  (point: string, idx: number) => {
                                    const isKpExpanded =
                                      expandedKeypoints[doc.id]?.has(idx) ||
                                      false;
                                    const directEvidence =
                                      evidenceByKeypoint.get(
                                        normalizeForMatch(point),
                                      ) || [];
                                    const extraction = extractions[doc.id];
                                    const derivedEvidence =
                                      !directEvidence.length && extraction
                                        ? deriveEvidenceForKeypoint(
                                            point,
                                            extraction,
                                          )
                                        : [];
                                    const evidence =
                                      directEvidence.length > 0
                                        ? directEvidence
                                        : derivedEvidence;

                                    const canShowSources =
                                      directEvidence.length > 0 ||
                                      !!extraction ||
                                      !!doc.url;

                                    return (
                                      <div
                                        key={idx}
                                        className="rounded-md bg-card/50 border border-border/50 overflow-hidden"
                                      >
                                        <div className="flex items-start gap-2.5 p-2">
                                          <div className="mt-1 h-1.5 w-1.5 rounded-full bg-violet-500 shrink-0" />
                                          <div className="flex-1 min-w-0">
                                            <div className="flex items-start justify-between gap-3">
                                              <span className="text-sm text-foreground/80 leading-snug">
                                                {point}
                                              </span>
                                              {canShowSources && (
                                                <button
                                                  type="button"
                                                  onClick={async () => {
                                                    if (!extractions[doc.id]) {
                                                      await ensureExtractionLoaded(
                                                        doc.id,
                                                      );
                                                    }
                                                    toggleKeypoint(doc.id, idx);
                                                  }}
                                                  className={cn(
                                                    "shrink-0 text-[11px] font-semibold px-2 py-1 rounded-md border transition-colors",
                                                    isKpExpanded
                                                      ? "bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 border-violet-200 dark:border-violet-800"
                                                      : "text-muted-foreground hover:text-foreground hover:bg-muted border-border",
                                                  )}
                                                >
                                                  {isKpExpanded
                                                    ? "Hide sources"
                                                    : "Sources"}
                                                </button>
                                              )}
                                            </div>

                                            <AnimatePresence>
                                              {isKpExpanded && (
                                                <motion.div
                                                  initial={{
                                                    height: 0,
                                                    opacity: 0,
                                                  }}
                                                  animate={{
                                                    height: "auto",
                                                    opacity: 1,
                                                  }}
                                                  exit={{
                                                    height: 0,
                                                    opacity: 0,
                                                  }}
                                                  transition={{ duration: 0.15 }}
                                                  className="overflow-hidden"
                                                >
                                                  <div className="mt-2 space-y-2 border-t border-border/60 pt-2">
                                                    {extractionLoading[
                                                      doc.id
                                                    ] &&
                                                    !extractions[doc.id] ? (
                                                      <div className="text-xs text-muted-foreground">
                                                        Loading sources…
                                                      </div>
                                                    ) : evidence.length > 0 ? (
                                                      evidence
                                                        .slice(0, 3)
                                                        .map((ev, j) => (
                                                          <div
                                                            key={j}
                                                            className="rounded-md bg-muted/40 border border-border/50 p-2"
                                                          >
                                                            <div className="text-xs text-muted-foreground mb-1 flex items-center justify-between gap-2">
                                                              <span className="truncate">
                                                                Source:{" "}
                                                                {doc.title ||
                                                                  "Document"}
                                                              </span>
                                                              <a
                                                                href={
                                                                  ev.url ||
                                                                  doc.url
                                                                }
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="inline-flex items-center gap-1 text-xs font-medium hover:text-foreground"
                                                              >
                                                                Open
                                                                <ExternalLink className="h-3 w-3 opacity-60" />
                                                              </a>
                                                            </div>
                                                            <blockquote className="text-xs leading-relaxed text-foreground/85 border-l-2 border-violet-300 dark:border-violet-700 pl-2">
                                                              {ev.quote}
                                                            </blockquote>
                                                          </div>
                                                        ))
                                                    ) : (
                                                      <div className="text-xs text-muted-foreground">
                                                        No exact quote found for
                                                        this keypoint yet.
                                                      </div>
                                                    )}
                                                  </div>
                                                </motion.div>
                                              )}
                                            </AnimatePresence>
                                          </div>
                                        </div>
                                      </div>
                                    );
                                  },
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
