// Consumer TOS-explainer shape. Mirrors the backend `ConsumerExplainer`
// pydantic roll-up. Every field is optional/defensive because the free-model
// output varies — unknown enum strings are tolerated and normalized at render
// time rather than failing the parse.

export type ConsumerGrade = "A" | "B" | "C" | "D" | "E";

export type ConsumerSeverity = "critical" | "high" | "medium" | "low";

export type ConsumerConfidence = "high" | "medium" | "low";

export interface SourceCitation {
  document_id: string;
  document_title?: string | null;
  document_type?: string | null;
  document_url: string;
  quote: string;
  section_title?: string | null;
  start_char?: number | null;
  end_char?: number | null;
  content_hash?: string | null;
  verified: boolean;
}

// One model backs watch_out_for and who_gets_your_data on the backend, so the
// shape is shared: `title` is the risk label or recipient name, `what_they_get`
// is set for recipients, `why` is the purpose for collected data.
export interface ConsumerCase {
  title?: string | null;
  means_for_you?: string | null;
  severity?: string | null;
  classification?: string | null;
  what_they_get?: string | null;
  why?: string | null;
  quote?: string | null;
  quote_status?: string | null;
  citation?: SourceCitation | null;
}

export interface ConsumerDataItem extends ConsumerCase {
  // How tied the data is to the reader's real identity, and whether the policy
  // says it is sold or shared for value.
  linkage_tier?: string | null;
  sold?: boolean | null;
}

export interface ActionStep {
  action?: string | null;
  applies_to?: string[] | null;
}

export interface ConsumerContradiction {
  topic?: string | null;
  what_one_doc_says?: string | null;
  what_another_says?: string | null;
  assume?: string | null;
}

export interface ConsumerRegionVerdict {
  region?: string | null;
  you_can?: string[] | null;
  you_cannot?: string[] | null;
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
  who_gets_your_data?: Array<ConsumerCase | string> | null;
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

function severityRank(raw: string | null | undefined): number {
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
// plain strings from cheaper models, or with null entries; coerce every shape
// (including null/undefined) to a stable object so callers can read fields
// without guarding each access.
export function asDataItem(
  item: ConsumerDataItem | string | null | undefined,
): ConsumerDataItem {
  if (!item) return {};
  return typeof item === "string" ? { title: item } : item;
}

export function asConsumerCase(
  item: ConsumerCase | string | null | undefined,
): ConsumerCase {
  if (!item) return {};
  return typeof item === "string" ? { title: item } : item;
}

export function asActionStep(
  item: ActionStep | string | null | undefined,
): ActionStep {
  if (!item) return {};
  return typeof item === "string" ? { action: item } : item;
}

// Only codes whose label isn't just the upper-cased code need an entry — the single
// place to localize them later. Anything else (eu, us, ae, sg, br, ...) falls back to
// its upper-cased form, so any region works without being listed.
const REGION_LABELS: Record<string, string> = {
  global: "Everyone",
  ca: "Canada",
  latam: "Latin America",
  apac: "Asia-Pacific",
  au: "Australia",
};

function regionLabel(code: string): string {
  const key = code.trim().toLowerCase();
  return REGION_LABELS[key] ?? code.trim().toUpperCase();
}

// Labels to show as scope badges: nothing when the step applies to everyone.
export function scopeLabels(codes: string[] | null | undefined): string[] {
  if (!codes || codes.length === 0) return [];
  const meaningful = codes.filter(
    (code) => code.trim().toLowerCase() !== "global",
  );
  return meaningful.map(regionLabel);
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
