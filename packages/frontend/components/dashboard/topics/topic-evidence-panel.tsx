"use client";

import {
  AlertTriangle,
  ExternalLink,
  Info,
  Shield,
  ShieldAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ProductTopicReport, TopicStanceBreakdown } from "@/types";

interface TopicEvidencePanelProps {
  topicStances?: TopicStanceBreakdown[] | null;
  topicReport?: ProductTopicReport | null;
  title?: string;
  showCitations?: boolean;
}

const stanceStyles: Record<
  TopicStanceBreakdown["stance"],
  { label: string; className: string; icon: typeof Shield }
> = {
  low_risk: {
    label: "Low Risk",
    className: "text-risk-low border-risk-low/20 bg-risk-low/5",
    icon: Shield,
  },
  moderate_risk: {
    label: "Moderate Risk",
    className: "text-risk-medium border-risk-medium/20 bg-risk-medium/5",
    icon: Info,
  },
  high_risk: {
    label: "High Risk",
    className: "text-risk-high border-risk-high/20 bg-risk-high/5",
    icon: ShieldAlert,
  },
  not_disclosed: {
    label: "Not Disclosed",
    className: "text-muted-foreground border-border bg-muted/5",
    icon: Info,
  },
  mixed: {
    label: "Conflicting",
    className: "text-risk-high border-risk-high/20 bg-risk-high/5",
    icon: AlertTriangle,
  },
};

function humanizeTopic(topic: string): string {
  return topic.replace(/_/g, " ");
}

export function TopicEvidencePanel({
  topicStances,
  topicReport,
  title = "Topic Evidence",
  showCitations = true,
}: TopicEvidencePanelProps) {
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
      topic_score: stance?.topic_score ?? item.topic_score,
      rationale: stance?.rationale ?? item.rationale,
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
    high_risk: 0,
    mixed: 1,
    moderate_risk: 2,
    low_risk: 3,
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
      <div className="p-6 border-b border-border flex items-center gap-3">
        <Shield className="h-5 w-5 text-foreground" strokeWidth={1.5} />
        <h3 className="text-[10px] uppercase tracking-[0.2em] font-medium text-foreground">
          {title}
        </h3>
      </div>

      <div className="divide-y divide-border">
        {allTopics.map((topic) => {
          const style = stanceStyles[topic.stance];
          const Icon = style.icon;
          return (
            <div key={topic.topic} className="p-5 space-y-3">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-foreground capitalize">
                    {humanizeTopic(topic.topic)}
                  </p>
                  {topic.rationale && (
                    <p className="text-xs text-muted-foreground">
                      {topic.rationale}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    size="sm"
                    className={cn("gap-1.5 border", style.className)}
                  >
                    <Icon className="h-3 w-3" />
                    {style.label}
                  </Badge>
                  {typeof topic.topic_score === "number" && (
                    <Badge variant="outline" size="sm">
                      Score: {topic.topic_score}/10
                    </Badge>
                  )}
                </div>
              </div>

              {topic.findings.length > 0 && (
                <div className="space-y-2">
                  {topic.findings.slice(0, 3).map((finding, idx) => (
                    <div
                      key={`${topic.topic}-f-${idx}`}
                      className="text-xs text-foreground/80"
                    >
                      - {finding.value}
                    </div>
                  ))}
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

              {showCitations && topic.findings.length > 0 && (
                <div className="space-y-2 pt-1">
                  {topic.findings
                    .flatMap((finding) => finding.citations || [])
                    .slice(0, 3)
                    .map((citation, idx) => (
                      <div
                        key={`${topic.topic}-quote-${idx}`}
                        className="rounded-none bg-muted/40 border border-border/50 p-2"
                      >
                        <div className="text-[11px] text-muted-foreground mb-1 flex items-center justify-between gap-2">
                          <span className="truncate">
                            Source:{" "}
                            {citation.document_title || citation.document_id}
                          </span>
                          {citation.document_url && (
                            <a
                              href={citation.document_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 hover:text-foreground"
                            >
                              Open
                              <ExternalLink className="h-3 w-3 opacity-60" />
                            </a>
                          )}
                        </div>
                        <blockquote className="text-xs text-foreground/85 border-l-2 border-foreground pl-2">
                          {citation.quote}
                        </blockquote>
                      </div>
                    ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
