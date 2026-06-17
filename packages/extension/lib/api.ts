/**
 * API client for Clausea extension
 */

const API_BASE_URL =
  import.meta.env.MODE === "development"
    ? "http://localhost:8000"
    : "https://api.clausea.co";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Verdict =
  | "very_user_friendly"
  | "user_friendly"
  | "moderate"
  | "pervasive"
  | "very_pervasive";

interface ExtensionCrawlError {
  url: string;
  error_type: string;
  error_message: string | null;
}

type ExtensionProductStatus =
  | "unknown"
  | "analyzing"
  | "failed"
  | "ready";

export interface ExtensionCheckResponse {
  found: boolean;
  slug: string | null;
  product_name: string | null;
  product_status: ExtensionProductStatus;
  pipeline_active: boolean;
  pipeline_failed: boolean;
  pipeline_error: string | null;
  crawl_errors: ExtensionCrawlError[] | null;
  verdict: Verdict | null;
  risk_score: number | null;
  one_line_summary: string | null;
  top_concerns: string[] | null;
  analysis_url: string | null;
}

export interface ExtensionAnalyzeResponse {
  status: "started" | "already_running" | "already_indexed";
  product_slug: string;
  product_name: string;
  job_id: string | null;
}

export interface RateLimitError extends Error {
  readonly requiresAuth: true;
  readonly loginUrl: string;
}

export function isRateLimitError(e: unknown): e is RateLimitError {
  return e instanceof Error && (e as RateLimitError).requiresAuth === true;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/**
 * Check if we have privacy analysis for a given URL.
 * Also returns whether a pipeline is already running for this domain.
 */
export async function checkUrl(url: string): Promise<ExtensionCheckResponse> {
  const response = await fetch(
    `${API_BASE_URL}/extension/check?url=${encodeURIComponent(url)}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    },
  );

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

/**
 * Trigger the analysis pipeline for a URL.
 *
 * Creates the product from URL metadata if it doesn't exist,
 * then starts the background pipeline. Idempotent per domain.
 *
 * seedUrls: policy-page URLs harvested from the rendered DOM footer. Passed
 * as high-priority crawl seeds so sites behind anti-bot walls can still be
 * analyzed when the server crawler cannot reach them.
 */
export async function analyzeUrl(
  url: string,
  extraHeaders?: Record<string, string>,
  seedUrls?: string[],
): Promise<ExtensionAnalyzeResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };

  const body: Record<string, unknown> = { url };
  if (seedUrls && seedUrls.length > 0) body.seed_urls = seedUrls;

  const response = await fetch(`${API_BASE_URL}/extension/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    if (response.status === 429 && detail?.requires_auth) {
      throw Object.assign(new Error("Login required to analyze more sites"), {
        requiresAuth: true as const,
        loginUrl: (detail.login_url ?? "https://clausea.co/sign-in") as string,
      }) as RateLimitError;
    }
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Analysis failed with status ${response.status}`,
    );
  }

  return response.json();
}

/**
 * Subscribe an email to be notified when analysis completes for a product.
 */
export async function subscribeEmail(
  productSlug: string,
  email: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/extension/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_slug: productSlug, email }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.detail ?? `Subscription failed with status ${response.status}`;
    throw new Error(message);
  }
}

// ---------------------------------------------------------------------------
// Verdict helpers
// ---------------------------------------------------------------------------

/**
 * Get verdict color category for styling
 */
export function getVerdictColor(verdict: Verdict | null): string {
  switch (verdict) {
    case "very_user_friendly":
    case "user_friendly":
      return "safe";
    case "moderate":
      return "caution";
    case "pervasive":
    case "very_pervasive":
      return "danger";
    default:
      return "gray";
  }
}

/**
 * Get verdict label for display
 */
export function getVerdictLabel(verdict: Verdict | null): string {
  switch (verdict) {
    case "very_user_friendly":
      return "Very Safe";
    case "user_friendly":
      return "Safe";
    case "moderate":
      return "Moderate";
    case "pervasive":
      return "Risky";
    case "very_pervasive":
      return "Very Risky";
    default:
      return "Unknown";
  }
}
