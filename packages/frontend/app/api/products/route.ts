import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";
import { productsPageSchema } from "@lib/schemas";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = searchParams.get("page") ?? "1";
    const limit = searchParams.get("limit") ?? "20";
    const search = searchParams.get("search") ?? "";

    const params = new URLSearchParams({ page, limit });
    if (search) params.set("search", search);

    const url = `${apiEndpoints.products()}?${params.toString()}`;
    const data = await httpJson(url, {
      method: "GET",
      schema: productsPageSchema,
    });

    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching products:", error);
    return NextResponse.json(
      { error: `Failed to fetch products` },
      { status: 500 },
    );
  }
}
