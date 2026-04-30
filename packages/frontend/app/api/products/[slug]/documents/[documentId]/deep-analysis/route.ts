import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string; documentId: string }> },
) {
  const { slug, documentId } = await params;

  try {
    const analysis = await httpJson(
      `${apiEndpoints.products()}/${slug}/documents/${documentId}/deep-analysis`,
      { method: "GET" },
    );

    return NextResponse.json(analysis);
  } catch (error) {
    console.error("Error fetching document deep analysis:", error);
    return NextResponse.json(
      { error: `Failed to fetch document deep analysis: ${error}` },
      { status: 500 },
    );
  }
}
