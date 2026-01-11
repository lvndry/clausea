"use client";

import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  FolderOpen,
  Link as LinkIcon,
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

interface DocumentExtraction {
  version: string;
  generated_at: string;
  source_content_hash: string;
  data_collected: Array<{ value: string; evidence: EvidenceSpan[] }>;
  data_purposes: Array<{ value: string; evidence: EvidenceSpan[] }>;
  data_collection_details: Array<{
    data_type: string;
    purposes: string[];
    evidence: EvidenceSpan[];
  }>;
  third_party_details: Array<{
    recipient: string;
    data_shared: string[];
    purpose?: string | null;
    risk_level: "low" | "medium" | "high";
    evidence: EvidenceSpan[];
  }>;
  your_rights: Array<{ value: string; evidence: EvidenceSpan[] }>;
  dangers: Array<{ value: string; evidence: EvidenceSpan[] }>;
  benefits: Array<{ value: string; evidence: EvidenceSpan[] }>;
  recommended_actions: Array<{ value: string; evidence: EvidenceSpan[] }>;
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

  const pools: Array<Array<{ value: string; evidence: EvidenceSpan[] }>> = [
    extraction.data_collected,
    extraction.data_purposes,
    extraction.your_rights,
    extraction.dangers,
    extraction.benefits,
    extraction.recommended_actions,
  ];

  const found: EvidenceSpan[] = [];
  for (const pool of pools) {
    for (const item of pool) {
      const value = normalizeForMatch(item.value);
      if (value && kp.includes(value) && item.evidence?.length) {
        found.push(...item.evidence);
        if (found.length >= 3) return found.slice(0, 3);
      }
    }
  }

  // Secondary pass: match third parties / data_collection_details keys
  for (const tp of extraction.third_party_details || []) {
    const recipient = normalizeForMatch(tp.recipient);
    if (recipient && kp.includes(recipient) && tp.evidence?.length) {
      found.push(...tp.evidence);
      if (found.length >= 3) return found.slice(0, 3);
    }
  }
  for (const dcd of extraction.data_collection_details || []) {
    const dt = normalizeForMatch(dcd.data_type);
    if (dt && kp.includes(dt) && dcd.evidence?.length) {
      found.push(...dcd.evidence);
      if (found.length >= 3) return found.slice(0, 3);
    }
  }

  return found.slice(0, 3);
}

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

    // Track document source clicked when expanding
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
                Legal documents analyzed for this product
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
          const hasSummary =
            doc.summary || (doc.keypoints && doc.keypoints.length > 0);
          const evidenceByKeypoint = new Map<string, EvidenceSpan[]>();
          if (
            doc.keypoints_with_evidence &&
            Array.isArray(doc.keypoints_with_evidence)
          ) {
            for (const entry of doc.keypoints_with_evidence) {
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
                className={cn("p-4", hasSummary && "cursor-pointer")}
                onClick={() => hasSummary && toggleExpanded(doc.id, doc.title)}
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
                      {hasSummary && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleExpanded(doc.id, doc.title);
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
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Expanded Content */}
              <AnimatePresence>
                {isExpanded && hasSummary && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 pt-2 border-t border-violet-200 dark:border-violet-800">
                      <div className="space-y-3">
                        {/* Summary */}
                        {doc.summary && (
                          <div className="text-sm text-foreground/90 leading-relaxed prose prose-sm dark:prose-invert max-w-none prose-p:my-2">
                            <MarkdownRenderer>{doc.summary}</MarkdownRenderer>
                          </div>
                        )}

                        {/* Keypoints */}
                        {doc.keypoints && doc.keypoints.length > 0 && (
                          <div className="pt-1">
                            <h5 className="text-[10px] font-bold text-violet-700 dark:text-violet-300 uppercase tracking-widest mb-2 flex items-center gap-2">
                              <span className="h-px w-4 bg-violet-300 dark:bg-violet-700" />
                              Key Insights
                            </h5>
                            <div className="space-y-1.5">
                              {doc.keypoints.map(
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
                                    !!doc.url; // allow fetch

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
                                                exit={{ height: 0, opacity: 0 }}
                                                transition={{ duration: 0.15 }}
                                                className="overflow-hidden"
                                              >
                                                <div className="mt-2 space-y-2 border-t border-border/60 pt-2">
                                                  {extractionLoading[doc.id] &&
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
