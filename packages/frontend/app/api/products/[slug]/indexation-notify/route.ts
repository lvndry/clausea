import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { http } from "@lib/http";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const response = await http(
    `${apiEndpoints.products()}/${slug}/indexation-notify`,
    {
      method: "POST",
      body: await request.text(),
      headers: { "Content-Type": "application/json" },
    },
  );

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type":
        response.headers.get("content-type") || "application/json",
    },
  });
}
