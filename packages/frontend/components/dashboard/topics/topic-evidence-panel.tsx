"use client";

import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Info,
  Shield,
  ShieldAlert,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { type KeyboardEvent, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  ProductTopicReport,
  TopicCitation,
  TopicStanceBreakdown,
} from "@/types";

interface TopicEvidencePanelProps {
  topicStances?: TopicStanceBreakdown[] | null;
  topicReport?: ProductTopicReport | null;
  title?: string;
  showCitations?: boolean;
  collapsibleTopics?: boolean;
}

const TOPIC_CITATION_PREVIEW_LIMIT = 5;

function normalizeQuoteForDedup(quote: string | null | undefined): string {
  return (quote || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/^["'“”‘’]+|["'“”‘’]+$/g, "")
    .replace(/[.,;:!?]+$/g, "")
    .replace(/licence/g, "license");
}

function collectTopicPreviewCitations(
  findings: Array<{ citations?: TopicCitation[] | null }>,
  limit: number,
): TopicCitation[] {
  const selected: TopicCitation[] = [];
  const seen = new Set<string>();

  for (const finding of findings) {
    for (const citation of finding.citations || []) {
      const key = `${citation.document_id}:${normalizeQuoteForDedup(citation.quote)}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      selected.push(citation);
      if (selected.length >= limit) {
        return selected;
      }
    }
  }

  return selected;
}

const stanceStyles: Record<
  TopicStanceBreakdown["stance"],
  { label: string; className: string; icon: typeof Shield }
> = {
  fair: {
    label: "Fair",
    className: "text-risk-low border-risk-low/20 bg-risk-low/5",
    icon: Shield,
  },
  concerning: {
    label: "Concerning",
    className: "text-risk-medium border-risk-medium/20 bg-risk-medium/5",
    icon: Info,
  },
  harmful: {
    label: "Harmful",
    className: "text-risk-high border-risk-high/20 bg-risk-high/5",
    icon: ShieldAlert,
  },
  not_disclosed: {
    label: "Not Disclosed",
    className: "text-muted-foreground border-border bg-muted/5",
    icon: Info,
  },
  conflicting: {
    label: "Conflicting",
    className: "text-risk-high border-risk-high/20 bg-risk-high/5",
    icon: AlertTriangle,
  },
};

function humanizeTopic(topic: string): string {
  return topic.replace(/_/g, " ");
}

function TopicCitationCard({
  citation,
  index,
  total,
  compact = false,
}: {
  citation: TopicCitation;
  index: number;
  total: number;
  compact?: boolean;
}) {
  const documentLabel =
    citation.document_title || citation.document_id || "Policy document";

  return (
    <figure
      className={cn(
        "rounded-none border border-border/60 bg-muted/30",
        compact ? "p-3" : "p-4",
      )}
    >
      <figcaption className="mb-2 flex flex-col gap-2 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-bold uppercase tracking-[0.18em] text-foreground">
              Evidence quote {index + 1}
              {total > 1 ? ` of ${total}` : ""}
            </span>
            {citation.verified && (
              <Badge variant="outline" size="sm" className="h-5 px-1.5">
                Verified
              </Badge>
            )}
          </div>
          <div className="truncate">
            From <span className="text-foreground/80">{documentLabel}</span>
            {citation.section_title ? ` - ${citation.section_title}` : ""}
          </div>
        </div>
        {citation.document_url && (
          <a
            href={citation.document_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-fit items-center gap-1 border border-border px-2 py-1 font-semibold text-foreground transition-colors hover:bg-background"
          >
            Open document
            <ExternalLink className="h-3 w-3 opacity-60" />
          </a>
        )}
      </figcaption>
      <blockquote className="border-l-2 border-foreground pl-3 text-sm leading-relaxed text-foreground/90">
        &ldquo;{citation.quote}&rdquo;
      </blockquote>
    </figure>
  );
}

export function TopicEvidencePanel({
  topicStances,
  topicReport,
  title = "Topic Evidence",
  showCitations = true,
  collapsibleTopics = false,
}: TopicEvidencePanelProps) {
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set());

  function toggleTopicExpanded(topicKey: string) {
    setExpandedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(topicKey)) {
        next.delete(topicKey);
      } else {
        next.add(topicKey);
      }
      return next;
    });
  }

  const stancesByTopic = new Map(
    (topicStances || []).map((stance) => [stance.topic, stance]),
  );
  const reportItems = topicReport?.topics ?? [];

  if (!topicStances?.length && !reportItems.length) {
    return null;
  }

  const mergedTopics = reportItems.map((item) => {
    const stance = stancesByTopic.get(item.topic);
    return {
      topic: item.topic,
      status: stance?.status ?? item.status,
      stance: stance?.stance ?? item.stance,
      rationale: stance?.rationale ?? item.rationale,
      rationale_key: stance?.rationale_key ?? item.rationale_key,
      rationale_params: stance?.rationale_params ?? item.rationale_params,
      headline_claim:
        stance?.headline_claim ??
        item.findings[0]?.value ??
        item.conflicts[0]?.description,
      supporting_citations:
        stance?.supporting_citations && stance.supporting_citations.length > 0
          ? stance.supporting_citations.slice(0, TOPIC_CITATION_PREVIEW_LIMIT)
          : collectTopicPreviewCitations(
              item.findings,
              TOPIC_CITATION_PREVIEW_LIMIT,
            ),
      conflict_note: stance?.conflict_note ?? item.conflicts[0]?.description,
      why_it_matters: stance?.why_it_matters,
      recommended_action: stance?.recommended_action,
      findings: item.findings,
      conflicts: item.conflicts,
    };
  });

  const topicsOnlyInStances = (topicStances || []).filter(
    (stance) => !reportItems.some((item) => item.topic === stance.topic),
  );

  const allTopics = [
    ...mergedTopics,
    ...topicsOnlyInStances.map((stance) => ({
      ...stance,
      findings: [],
      conflicts: [],
    })),
  ];

  const stanceWeight: Record<string, number> = {
    harmful: 0,
    conflicting: 1,
    concerning: 2,
    fair: 3,
    not_disclosed: 4,
  };
  allTopics.sort((a, b) => {
    const wA = stanceWeight[a.stance] ?? 99;
    const wB = stanceWeight[b.stance] ?? 99;
    if (wA !== wB) return wA - wB;
    return a.topic.localeCompare(b.topic);
  });

  return (
    <div className="border border-border bg-background">
      <div className="p-6 border-b border-border flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <Shield
            className="mt-0.5 h-5 w-5 text-foreground"
            strokeWidth={1.5}
          />
          <div>
            <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
              {title}
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              {showCitations
                ? "Trace each topic back to exact quotes from the policies we analyzed."
                : "A quick topic summary with representative evidence where available."}
            </p>
          </div>
        </div>
      </div>

      <div className="divide-y divide-border">
        {allTopics.map((topic) => {
          const style = stanceStyles[topic.stance];
          const Icon = style.icon;
          const previewCitations = showCitations
            ? collectTopicPreviewCitations(
                topic.findings,
                TOPIC_CITATION_PREVIEW_LIMIT,
              )
            : topic.supporting_citations &&
                topic.supporting_citations.length > 0
              ? topic.supporting_citations.slice(
                  0,
                  TOPIC_CITATION_PREVIEW_LIMIT,
                )
              : collectTopicPreviewCitations(
                  topic.findings,
                  TOPIC_CITATION_PREVIEW_LIMIT,
                );
          const isExpanded =
            !collapsibleTopics || expandedTopics.has(topic.topic);
          const panelId = `topic-evidence-${topic.topic}`;

          const topicDetails = (
            <>
              {topic.headline_claim && (
                <p
                  className={cn(
                    "text-sm leading-relaxed",
                    topic.stance === "fair"
                      ? "text-risk-low"
                      : "text-foreground/90",
                  )}
                >
                  {topic.stance === "fair" ? "Good practice: " : ""}
                  {topic.headline_claim}
                </p>
              )}
              {topic.rationale && (
                <p className="text-xs text-muted-foreground">
                  {topic.rationale}
                </p>
              )}
              {topic.why_it_matters && (
                <p className="text-xs text-muted-foreground">
                  Why it matters: {topic.why_it_matters}
                </p>
              )}

              {topic.recommended_action && (
                <div className="rounded-none border border-border/60 bg-muted/20 p-2 text-xs text-foreground/85">
                  <span className="font-semibold">Action:</span>{" "}
                  {topic.recommended_action}
                </div>
              )}

              {!showCitations && previewCitations.length > 0 && (
                <div className="space-y-2">
                  {previewCitations.map((citation, idx) => (
                    <TopicCitationCard
                      key={`${topic.topic}-overview-citation-${idx}`}
                      citation={citation}
                      index={idx}
                      total={previewCitations.length}
                      compact
                    />
                  ))}
                </div>
              )}

              {topic.conflict_note && topic.conflicts.length === 0 && (
                <div className="text-xs text-risk-high border-l border-risk-high/40 pl-2">
                  {topic.conflict_note}
                </div>
              )}

              {topic.findings.length > 0 && (
                <div className="space-y-2">
                  {topic.findings.slice(0, 5).map((finding, idx) => {
                    const documentCount = finding.document_ids?.length ?? 0;
                    return (
                      <div
                        key={`${topic.topic}-f-${idx}`}
                        className={cn(
                          "text-xs leading-relaxed border-l pl-2",
                          topic.stance === "fair"
                            ? "text-risk-low border-risk-low/40"
                            : "text-foreground/80 border-border/60",
                        )}
                      >
                        {topic.stance === "fair" ? "+ " : "- "}
                        {finding.value}
                        {documentCount > 1 && (
                          <Badge
                            variant="outline"
                            size="sm"
                            className="ml-2 align-middle"
                          >
                            Stated in {documentCount} documents
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {topic.conflicts.length > 0 && (
                <div className="space-y-2">
                  {topic.conflicts.slice(0, 2).map((conflict, idx) => (
                    <div
                      key={`${topic.topic}-c-${idx}`}
                      className="text-xs text-risk-high border-l border-risk-high/40 pl-2"
                    >
                      {conflict.description}
                    </div>
                  ))}
                </div>
              )}

              {showCitations && previewCitations.length > 0 && (
                <div className="space-y-2 pt-1">
                  {previewCitations.map((citation, idx) => (
                    <TopicCitationCard
                      key={`${topic.topic}-quote-${idx}`}
                      citation={citation}
                      index={idx}
                      total={previewCitations.length}
                    />
                  ))}
                </div>
              )}
            </>
          );

          return (
            <div key={topic.topic} className="p-5">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div
                  className={cn(
                    "flex min-w-0 flex-1 items-start gap-2",
                    collapsibleTopics && "cursor-pointer",
                  )}
                  {...(collapsibleTopics
                    ? {
                        role: "button" as const,
                        tabIndex: 0,
                        onClick: () => toggleTopicExpanded(topic.topic),
                        onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            toggleTopicExpanded(topic.topic);
                          }
                        },
                      }
                    : {})}
                >
                  {collapsibleTopics &&
                    (isExpanded ? (
                      <ChevronDown
                        className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                    ) : (
                      <ChevronRight
                        className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                    ))}
                  <p className="text-sm font-semibold text-foreground capitalize">
                    {humanizeTopic(topic.topic)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    size="sm"
                    className={cn("gap-1.5 border", style.className)}
                  >
                    <Icon className="h-3 w-3" />
                    {style.label}
                  </Badge>
                  {collapsibleTopics && (
                    <button
                      type="button"
                      onClick={() => toggleTopicExpanded(topic.topic)}
                      aria-expanded={isExpanded}
                      aria-controls={panelId}
                      className={cn(
                        "flex items-center gap-1.5 rounded-none px-2.5 py-1.5 text-xs font-medium transition-all shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                        isExpanded
                          ? "bg-muted text-foreground"
                          : "text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {isExpanded ? (
                        <>
                          <ChevronDown
                            className="h-3.5 w-3.5"
                            aria-hidden="true"
                          />
                          Close
                        </>
                      ) : (
                        <>
                          <ChevronRight
                            className="h-3.5 w-3.5"
                            aria-hidden="true"
                          />
                          Details
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>

              {collapsibleTopics ? (
                <AnimatePresence initial={false}>
                  {isExpanded && (
                    <motion.div
                      id={panelId}
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-3 pt-3">{topicDetails}</div>
                    </motion.div>
                  )}
                </AnimatePresence>
              ) : (
                <div className="space-y-3 pt-3">{topicDetails}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
