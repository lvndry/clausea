import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { http } from "@lib/http";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string; documentId: string }> },
) {
  const { slug, documentId } = await params;
  const response = await http(
    `${apiEndpoints.products()}/${slug}/documents/${documentId}/deep-analysis`,
    { method: "GET" },
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
