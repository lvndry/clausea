import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  try {
    const overview = await httpJson(
      `${apiEndpoints.products()}/${slug}/overview`,
      {
        method: "GET",
      },
    );
    return NextResponse.json(overview);
  } catch (error) {
    console.error("Error fetching product overview:", error);
    return NextResponse.json(
      { error: `Failed to fetch product overview: ${error}` },
      { status: 500 },
    );
  }
}
