/** Terminal and in-flight pipeline job statuses (shared by API route and poll UI). */
export type PipelineJobStatus =
  | "pending"
  | "crawling"
  | "synthesising"
  | "summarizing"
  | "generating_overview"
  | "completed"
  | "failed"
  | "no_documents"
  | "robots_blocked"
  | "access_denied"
  | "no_policy_found"
  | "site_unavailable"
  | "analysis_failed"
  | "thin_evidence"
  | "interrupted";

export const TERMINAL_PIPELINE_STATUSES: PipelineJobStatus[] = [
  "completed",
  "failed",
  "no_documents",
  "robots_blocked",
  "access_denied",
  "no_policy_found",
  "site_unavailable",
  "analysis_failed",
  "thin_evidence",
  "interrupted",
];
