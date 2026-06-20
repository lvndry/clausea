import { NextResponse } from "next/server";

function parseBackendErrorMessage(error: unknown): {
  status: number;
  detail: string;
} {
  if (!(error instanceof Error)) {
    return { status: 500, detail: "Request failed" };
  }

  const match = error.message.match(/^Client HTTP (\d+) [^:]*: (.*)$/s);
  if (!match) {
    return { status: 500, detail: error.message || "Request failed" };
  }

  const status = Number.parseInt(match[1], 10);
  const rawBody = match[2]?.trim() ?? "";

  try {
    const parsed = JSON.parse(rawBody) as { detail?: string; error?: string };
    const detail = parsed.detail || parsed.error;
    if (detail) {
      return { status, detail };
    }
  } catch {
    // Fall through to raw body
  }

  return {
    status,
    detail: rawBody || error.message || "Request failed",
  };
}

export function subscriptionProxyError(error: unknown): NextResponse {
  const { status, detail } = parseBackendErrorMessage(error);
  console.error("Subscription proxy error:", error);
  return NextResponse.json({ detail }, { status });
}
