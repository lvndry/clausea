export type Verdict =
  | "very_user_friendly"
  | "user_friendly"
  | "moderate"
  | "pervasive"
  | "very_pervasive";

export interface DataPurposeLink {
  data_type: string;
  purposes: string[];
}

export interface ThirdPartyRecipient {
  recipient: string;
  data_shared: string[];
  purpose?: string | null;
  risk_level: "low" | "medium" | "high";
}

export interface DetailedScore {
  score: number;
  justification: string;
}

export interface DetailedScores {
  transparency: DetailedScore;
  data_collection_scope: DetailedScore;
  user_control: DetailedScore;
  third_party_sharing: DetailedScore;
}

export interface PrivacySignalsData {
  sells_data: "yes" | "no" | "unclear";
  cross_site_tracking: "yes" | "no" | "unclear";
  account_deletion: "self_service" | "request_required" | "not_specified";
  data_retention_summary?: string | null;
  consent_model: "opt_in" | "opt_out" | "mixed" | "not_specified";
}

export interface CoverageItem {
  category: string;
  status: "found" | "missing" | "ambiguous" | "not_analyzed";
  notes?: string | null;
}

export interface TopicStanceBreakdown {
  topic: string;
  status: "found" | "missing" | "not_disclosed" | "ambiguous";
  stance:
    | "low_risk"
    | "moderate_risk"
    | "high_risk"
    | "not_disclosed"
    | "mixed";
  topic_score?: number | null;
  rationale?: string | null;
  rationale_key?: string | null;
  rationale_params?: Record<string, string | number | null> | null;
  evidence_count?: number | null;
  document_count?: number | null;
  headline_claim?: string | null;
  supporting_citations?: TopicCitation[] | null;
  conflict_note?: string | null;
  why_it_matters?: string | null;
  recommended_action?: string | null;
}

export interface ComplianceBreakdown {
  score: number;
  status: "Compliant" | "Partially Compliant" | "Non-Compliant" | "Unknown";
  strengths: string[];
  gaps: string[];
  assessment_notes?: string | null;
}

export interface ProductOverview {
  product_name: string;
  product_slug: string;
  company_name?: string | null;
  last_updated: string;
  verdict?: Verdict | null;
  risk_score?: number | null;
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
  topic_stances?: TopicStanceBreakdown[] | null;
  coverage?: CoverageItem[] | null;
  contract_clauses?: string[] | null;
}

export interface EvidenceSpan {
  document_id: string;
  url: string;
  content_hash?: string | null;
  quote: string;
  start_char?: number | null;
  end_char?: number | null;
  section_title?: string | null;
}

export interface KeypointWithEvidence {
  keypoint: string;
  evidence: EvidenceSpan[];
}

export interface CriticalClause {
  clause_type: string;
  section_title?: string | null;
  quote: string;
  risk_level: "low" | "medium" | "high" | "critical";
  plain_english: string;
  why_notable: string;
  analysis: string;
  compliance_impact: string[];
}

export interface DocumentRiskBreakdown {
  overall_risk: number;
  risk_by_category: Record<string, number>;
  top_concerns: string[];
  positive_protections: string[];
  missing_information: string[];
}

export interface DocumentSection {
  section_title: string;
  content: string;
  importance: "low" | "medium" | "high" | "critical";
  analysis: string;
  related_clauses: string[];
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
  keypoints_with_evidence?: KeypointWithEvidence[] | null;
  critical_clauses?: CriticalClause[] | null;
  document_risk_breakdown?: DocumentRiskBreakdown | null;
  key_sections?: DocumentSection[] | null;
}

export interface CrawlError {
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

export interface FailedCrawlJob {
  error: string | null;
  error_detail: string | null;
  crawl_errors: CrawlError[];
  documents_stored?: number;
}

export interface TopicCitation {
  document_id: string;
  document_title?: string | null;
  document_url?: string | null;
  quote: string;
  section_title?: string | null;
  verified: boolean;
}

export interface TopicFinding {
  value: string;
  document_ids: string[];
  attributes: Record<string, unknown>[];
  citations: TopicCitation[];
}

export interface TopicConflict {
  description: string;
  severity?: string | null;
  document_ids: string[];
  citations: TopicCitation[];
}

export interface TopicReportItem {
  topic: string;
  coverage_status: "found" | "missing" | "ambiguous" | "not_analyzed";
  status: "found" | "missing" | "not_disclosed" | "ambiguous";
  stance:
    | "low_risk"
    | "moderate_risk"
    | "high_risk"
    | "not_disclosed"
    | "mixed";
  topic_score?: number | null;
  rationale?: string | null;
  rationale_key?: string | null;
  rationale_params?: Record<string, string | number | null> | null;
  findings: TopicFinding[];
  conflicts: TopicConflict[];
}

export interface ProductTopicReport {
  product_slug: string;
  generated_at?: string | null;
  topics: TopicReportItem[];
}
