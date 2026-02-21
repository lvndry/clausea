import { NextRequest, NextResponse } from "next/server";

import { getBackendUrl } from "@lib/config";
import { httpJson } from "@lib/http";

interface CrawlResponse {
  job_id: string;
  product_slug: string;
  product_name: string;
  status: string;
  message: string;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const url = getBackendUrl("/pipeline/crawl");

    const result = await httpJson<CrawlResponse>(url, {
      method: "POST",
      body,
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Error starting pipeline:", error);
    return NextResponse.json(
      { error: `Failed to start pipeline: ${error}` },
      { status: 500 },
    );
  }
}
