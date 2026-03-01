import { NextRequest, NextResponse } from "next/server";

import { getBackendUrl } from "@lib/config";
import { httpJson } from "@lib/http";

interface PipelineStep {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

interface PipelineJob {
  id: string;
  product_slug: string;
  product_name: string;
  url: string;
  status: string;
  steps: PipelineStep[];
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  documents_found: number;
  documents_stored: number;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const productSlug = searchParams.get("product_slug");

    if (!productSlug) {
      return NextResponse.json(
        { error: "product_slug is required" },
        { status: 400 },
      );
    }

    const backendUrl = getBackendUrl(
      `/pipeline/active?product_slug=${encodeURIComponent(productSlug)}`,
    );
    const job = await httpJson<PipelineJob>(backendUrl, { method: "GET" });
    return NextResponse.json(job);
  } catch (error: unknown) {
    // 404 from backend means no active job — surface that cleanly
    if (error instanceof Error && error.message.includes("404")) {
      return NextResponse.json(null, { status: 404 });
    }
    console.error("Error fetching active pipeline job:", error);
    return NextResponse.json(
      { error: `Failed to fetch active pipeline job: ${error}` },
      { status: 500 },
    );
  }
}
