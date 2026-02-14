import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(request: NextRequest) {
  try {
    const url = apiEndpoints.products();
    const products = await httpJson(url, {
      method: "GET",
    });

    // Return the products with caching headers
    return NextResponse.json(products, {
      headers: {
        "Cache-Control": "public, max-age=300", // Cache for 5 minutes
      },
    });
  } catch (error) {
    console.error("Error fetching products:", error);
    return NextResponse.json(
      { error: `Failed to fetch products: ${error}` },
      { status: 500 },
    );
  }
}
