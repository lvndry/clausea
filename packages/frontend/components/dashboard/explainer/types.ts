// Consumer TOS-explainer shape. Mirrors the backend `ConsumerExplainer`
// pydantic roll-up. Every field is optional/defensive because the free-model
// output varies — unknown enum strings are tolerated and normalized at render
// time rather than failing the parse.

export type ConsumerGrade = "A" | "B" | "C" | "D" | "E";

export type ConsumerSeverity = "critical" | "high" | "medium" | "low";

export type ConsumerConfidence = "high" | "medium" | "low";

export type QuoteStatus = "from_extraction" | "none";

export interface ConsumerCase {
  title?: string | null;
  means_for_you?: string | null;
  severity?: string | null;
  classification?: string | null;
  quote?: string | null;
  quote_status?: string | null;
}

export interface ConsumerDataItem {
  label?: string | null;
  detail?: string | null;
  sensitivity?: string | null;
}

export interface ActionStep {
  action?: string | null;
  detail?: string | null;
  region?: string | null;
}

export interface ConsumerContradiction {
  title?: string | null;
  description?: string | null;
  document_a?: string | null;
  document_b?: string | null;
  impact?: string | null;
}

export interface ConsumerRegionVerdict {
  region?: string | null;
  summary?: string | null;
  rights?: string[] | null;
}

export interface ConsumerRecipient {
  recipient?: string | null;
  data_shared?: string[] | null;
  purpose?: string | null;
}

export interface ConsumerSilentTopic {
  topic: string;
  why_it_matters?: string | null;
}

export interface ConsumerExplainer {
  headline?: string | null;
  tl_dr?: string | null;
  bottom_line?: string | null;
  grade?: string | null;
  grade_reason?: string | null;
  critical_findings_count?: number | null;
  confidence?: string | null;
  the_deal?: string | null;

  biggest_risks?: ConsumerCase[] | null;
  watch_out_for?: ConsumerCase[] | null;

  what_they_collect?: Array<ConsumerDataItem | string> | null;
  who_gets_your_data?: Array<ConsumerRecipient | string> | null;
  good_to_know?: string[] | null;
  silent_on?: Array<ConsumerSilentTopic | string> | null;

  // Backend (ConsumerExplainer) emits `contradictions`; `conflicts` kept as a
  // fallback alias since the roll-up prompt used that name.
  contradictions?: ConsumerContradiction[] | null;
  conflicts?: ConsumerContradiction[] | null;

  rights_by_region?: ConsumerRegionVerdict[] | null;
  region_verdicts?: ConsumerRegionVerdict[] | null;

  what_you_can_do?: Array<ActionStep | string> | null;
}

const GRADES: readonly ConsumerGrade[] = ["A", "B", "C", "D", "E"];

export function normalizeGrade(
  raw: string | null | undefined,
): ConsumerGrade | null {
  if (!raw) return null;
  const upper = raw.trim().toUpperCase();
  return (GRADES as readonly string[]).includes(upper)
    ? (upper as ConsumerGrade)
    : null;
}

const SEVERITIES: readonly ConsumerSeverity[] = [
  "critical",
  "high",
  "medium",
  "low",
];

export function normalizeSeverity(
  raw: string | null | undefined,
): ConsumerSeverity {
  const lower = (raw ?? "").trim().toLowerCase();
  return (SEVERITIES as readonly string[]).includes(lower)
    ? (lower as ConsumerSeverity)
    : "medium";
}

const SEVERITY_RANK: Record<ConsumerSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export function severityRank(raw: string | null | undefined): number {
  return SEVERITY_RANK[normalizeSeverity(raw)];
}

export function normalizeConfidence(
  raw: string | null | undefined,
): ConsumerConfidence | null {
  const lower = (raw ?? "").trim().toLowerCase();
  if (lower === "high" || lower === "medium" || lower === "low") {
    return lower;
  }
  return null;
}

export function hasCitation(quoteStatus: string | null | undefined): boolean {
  return (quoteStatus ?? "").trim().toLowerCase() === "from_extraction";
}

// `what_they_collect` / `who_gets_your_data` / `what_you_can_do` may arrive as
// plain strings from cheaper models; coerce both shapes to a stable object.
export function asDataItem(item: ConsumerDataItem | string): ConsumerDataItem {
  return typeof item === "string" ? { label: item } : item;
}

export function asRecipient(
  item: ConsumerRecipient | string,
): ConsumerRecipient {
  return typeof item === "string" ? { recipient: item } : item;
}

export function asActionStep(item: ActionStep | string): ActionStep {
  return typeof item === "string" ? { action: item } : item;
}

// `watch_out_for` is the canonical key; `biggest_risks` is an accepted alias.
export function resolveWatchOutFor(
  explainer: ConsumerExplainer,
): ConsumerCase[] {
  const cases = explainer.watch_out_for ?? explainer.biggest_risks ?? [];
  return [...cases].sort(
    (a, b) => severityRank(a.severity) - severityRank(b.severity),
  );
}

// `tl_dr` is the canonical key; `bottom_line` is the pydantic alias.
export function resolveTlDr(explainer: ConsumerExplainer): string | null {
  return explainer.tl_dr ?? explainer.bottom_line ?? null;
}

// `rights_by_region` is canonical; `region_verdicts` is an accepted alias.
export function resolveRegionVerdicts(
  explainer: ConsumerExplainer,
): ConsumerRegionVerdict[] {
  return explainer.rights_by_region ?? explainer.region_verdicts ?? [];
}
