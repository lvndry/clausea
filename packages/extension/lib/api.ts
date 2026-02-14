/**
 * API client for Clausea extension
 */

const API_BASE_URL =
  import.meta.env.MODE === "development"
    ? "http://localhost:8000"
    : "https://api.clausea.co";

export type Verdict =
  | "very_user_friendly"
  | "user_friendly"
  | "moderate"
  | "pervasive"
  | "very_pervasive";

export interface ExtensionCheckResponse {
  found: boolean;
  slug: string | null;
  product_name: string | null;
  verdict: Verdict | null;
  risk_score: number | null;
  one_line_summary: string | null;
  top_concerns: string[] | null;
  analysis_url: string | null;
}

/**
 * Check if we have privacy analysis for a given URL
 */
export async function checkUrl(url: string): Promise<ExtensionCheckResponse> {
  const response = await fetch(
    `${API_BASE_URL}/extension/check?url=${encodeURIComponent(url)}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

/**
 * Get all supported domains
 */
export async function getSupportedDomains(): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/extension/domains`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

export async function requestSupport(url: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/extension/request-support`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url, source: "browser_extension" }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
  }
}

/**
 * Get verdict color for styling
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
