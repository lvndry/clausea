import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string; documentId: string }> },
) {
  const { slug, documentId } = await params;

  try {
    const res = await fetch(
      `${apiEndpoints.products()}/${slug}/documents/${documentId}/deep-analysis`,
      { method: "GET" },
    );

    const body = await res.text();

    if (!res.ok) {
      return new NextResponse(body, {
        status: res.status,
        headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
      });
    }

    return new NextResponse(body, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Error fetching document deep analysis:", error);
    return NextResponse.json(
      { error: `Failed to fetch document deep analysis: ${error}` },
      { status: 500 },
    );
  }
}
