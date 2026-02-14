import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  try {
    const documents = await httpJson(
      `${apiEndpoints.products()}/${slug}/documents`,
      { method: "GET" },
    );
    return NextResponse.json(documents);
  } catch (error) {
    console.error("Error fetching product documents:", error);
    return NextResponse.json(
      { error: `Failed to fetch product documents: ${error}` },
      { status: 500 },
    );
  }
}
