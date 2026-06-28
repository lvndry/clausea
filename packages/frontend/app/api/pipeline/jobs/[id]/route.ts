import { NextRequest, NextResponse } from "next/server";

import type { CrawlError } from "@/types";
import { getBackendUrl } from "@lib/config";
import { httpJson } from "@lib/http";

type PipelineJobStatus =
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

interface PipelineStep {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  message: string | null;
  progress_current: number | null;
  progress_total: number | null;
  progress_percent: number | null;
  started_at: string | null;
  completed_at: string | null;
}

interface CrawlSkip {
  url: string;
  reason: string;
  detail: string | null;
}

interface PipelineJob {
  id: string;
  product_slug: string;
  product_name: string;
  url: string;
  status: PipelineJobStatus;
  steps: PipelineStep[];
  error: string | null;
  error_detail: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  documents_found: number;
  documents_stored: number;
  crawl_errors: CrawlError[];
  crawl_skip_reasons: CrawlSkip[];
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const url = getBackendUrl(`/pipeline/jobs/${id}`);
    const job = await httpJson<PipelineJob>(url, {
      method: "GET",
    });

    return NextResponse.json(job);
  } catch (error) {
    console.error("Error fetching pipeline job:", error);
    return NextResponse.json(
      { error: `Failed to fetch pipeline job` },
      { status: 500 },
    );
  }
}
