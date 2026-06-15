import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const slug = searchParams.get("slug");

    if (!slug) {
      return NextResponse.json(
        { error: "slug parameter is required" },
        { status: 400 },
      );
    }

    const product = await httpJson<{
      logo?: string | null;
      domains?: string[];
    }>(`${apiEndpoints.products()}/${slug}`, { method: "GET" });

    let logo = product.logo;

    if (!logo && product.domains) {
      let domain = product.domains[0];

      domain = domain.replace(/^https?:\/\//, "");

      const logoDevToken = process.env.LOGO_DEV_PUBLIC_KEY;

      if (logoDevToken) {
        logo = `https://img.logo.dev/${domain}?token=${logoDevToken}`;
      }
    }

    // Logos are effectively static; let the browser/CDN cache them so we don't
    // refetch (and re-hit the backend) on every navigation. Stale-while-revalidate
    // keeps it fresh in the background.
    return NextResponse.json(
      { logo },
      {
        headers: {
          "Cache-Control":
            "public, max-age=86400, stale-while-revalidate=604800",
        },
      },
    );
  } catch (error) {
    console.error("Error fetching logo:", error);
    return NextResponse.json(
      { error: `Failed to fetch logo` },
      { status: 500 },
    );
  }
}
