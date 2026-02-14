import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string; documentId: string }> },
) {
  const { slug, documentId } = await params;
  const url = new URL(request.url);
  const forceRegenerate = url.searchParams.get("force_regenerate");

  try {
    const qs = new URLSearchParams();
    if (forceRegenerate !== null) {
      qs.set("force_regenerate", forceRegenerate);
    }
    const suffix = qs.toString() ? `?${qs.toString()}` : "";

    const extraction = await httpJson(
      `${apiEndpoints.products()}/${slug}/documents/${documentId}/extraction${suffix}`,
      { method: "GET" },
    );

    return NextResponse.json(extraction);
  } catch (error) {
    console.error("Error fetching document extraction:", error);
    return NextResponse.json(
      { error: `Failed to fetch document extraction: ${error}` },
      { status: 500 },
    );
  }
}
