import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { http } from "@lib/http";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  try {
    const response = await http(`${apiEndpoints.products()}/${slug}/topics`, {
      method: "GET",
    });
    const body = await response.text();

    if (response.ok) {
      return new NextResponse(body, {
        status: response.status,
        headers: {
          "Content-Type":
            response.headers.get("content-type") || "application/json",
        },
      });
    }

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    console.error("Error fetching product topics:", error);
    return NextResponse.json(
      { error: `Failed to fetch product topics` },
      { status: 500 },
    );
  }
}
