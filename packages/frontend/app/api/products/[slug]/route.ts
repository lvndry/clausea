import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { http } from "@lib/http";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  try {
    const response = await http(`${apiEndpoints.products()}/${slug}`, {
      method: "GET",
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      return NextResponse.json(
        { error: text || response.statusText },
        { status: response.status },
      );
    }

    const product = await response.json();
    return NextResponse.json(product);
  } catch (error) {
    console.error("Error fetching product:", error);
    return NextResponse.json(
      { error: `Failed to fetch product: ${error}` },
      { status: 500 },
    );
  }
}
