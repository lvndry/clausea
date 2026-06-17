import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";
import { productsPageSchema } from "@lib/schemas";
import type { z } from "zod";

type ProductsPage = z.infer<typeof productsPageSchema>;

function enrichLogos(data: ProductsPage): ProductsPage {
  const token = process.env.LOGO_DEV_API_KEY;
  if (!token) return data;
  return {
    ...data,
    items: data.items.map((item) => {
      if (item.logo || !item.domains?.length) return item;
      const domain = item.domains[0].replace(/^https?:\/\//, "");
      return { ...item, logo: `https://img.logo.dev/${domain}?token=${token}` };
    }),
  };
}

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

    return NextResponse.json(enrichLogos(data));
  } catch (error) {
    console.error("Error fetching products:", error);
    return NextResponse.json(
      { error: `Failed to fetch products` },
      { status: 500 },
    );
  }
}
