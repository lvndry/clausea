// Maps a backend PipelineErrorCode to user-facing copy. The API returns a
// stable machine code in `job.error`; the frontend owns the phrasing. Unknown
// codes fall back to `error_detail` and then a generic message.

export const PIPELINE_ERROR_CODE_MESSAGES: Record<string, string> = {
  product_not_found:
    "We couldn't find this product. Please try submitting the URL again.",
  crawl_robots_blocked:
    "This site's robots.txt blocks automated access, so we couldn't read its policy documents. That's a restriction set by the site, not an error on our end. You'll need to review their policies manually.",
  crawl_failed:
    "We couldn't crawl this site successfully, so no policy documents were found. Please try again later.",
  no_documents_found:
    "We crawled this site but couldn't find any policy documents to analyze.",
  all_analysis_failed:
    "We found documents but couldn't analyze any of them. This is usually a temporary issue. Please try again.",
  core_docs_unanalyzed:
    "We couldn't analyze the core policy documents (privacy/terms), so we can't build a reliable overview. This is usually a temporary issue. Please try again.",
  overview_not_persisted:
    "We analyzed the documents but couldn't generate the overview. Please try again.",
  internal_error: "Something went wrong while analyzing this site.",
  timed_out:
    "Analysis took too long and timed out. Please try again, as large sites may need another attempt.",
  stalled:
    "Analysis stalled with no progress, usually on a site that's hard to crawl or a temporary issue. Please try again.",
  interrupted:
    "Analysis was interrupted by a worker restart and will resume automatically.",
  orphaned:
    "The analysis worker lost contact with this job (restart, crash, or missing heartbeats). It will be retried automatically.",
  access_denied:
    "This site actively blocked our crawler — likely Cloudflare or similar bot protection. This is a restriction set by the site. You can visit their site directly to read their policies.",
  no_policy_found:
    "We successfully crawled this site but couldn't find any privacy policy, terms of service, or cookie policy pages. The site may use a non-standard URL structure.",
  site_unavailable:
    "We couldn't reach this site — it may be temporarily down, the domain may have moved, or a network issue prevented access. Please try again later.",
  analysis_failed:
    "We retrieved the policy documents but encountered an error during AI analysis. This is temporary — please try again.",
};

export function resolvePipelineErrorMessage(
  error: string | null | undefined,
  errorDetail?: string | null,
): string {
  if (error && PIPELINE_ERROR_CODE_MESSAGES[error]) {
    return PIPELINE_ERROR_CODE_MESSAGES[error];
  }
  if (errorDetail) return errorDetail;
  return "Something went wrong.";
}
