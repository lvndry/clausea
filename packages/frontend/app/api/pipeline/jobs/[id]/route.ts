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
      { error: `Failed to fetch pipeline job: ${error}` },
      { status: 500 },
    );
  }
}
