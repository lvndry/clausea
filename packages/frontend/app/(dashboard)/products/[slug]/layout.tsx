import type { Metadata } from "next";
import { headers } from "next/headers";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

interface ProductOverview {
  name: string;
  slug: string;
  company_name?: string | null;
  one_line_summary?: string;
  risk_score?: number;
  verdict?:
    | "very_user_friendly"
    | "user_friendly"
    | "moderate"
    | "pervasive"
    | "very_pervasive";
}

function humanizeSlug(slug: string): string {
  return slug
    .split(/[-_]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function resolveOriginFromHeaders(headerList: Headers): string | null {
  const explicit = process.env.NEXT_PUBLIC_APP_URL?.replace(/\/$/, "");
  if (explicit) {
    return explicit;
  }
  const host = headerList.get("x-forwarded-host") ?? headerList.get("host");
  if (!host) {
    return null;
  }
  const proto = headerList.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}

type ProductMetadataFetch =
  | { kind: "ok"; product: ProductOverview }
  | { kind: "not_found" }
  | { kind: "uncertain"; displayName: string };

/**
 * Load product for SEO metadata via the same Next.js API route the client uses,
 * forwarding the request cookies so Clerk auth matches. A direct backend fetch
 * returns 401 (no Bearer token) and was incorrectly shown as "Product Not Found".
 */
async function fetchProductForMetadata(
  slug: string,
): Promise<ProductMetadataFetch> {
  try {
    const headerList = await headers();
    const origin = resolveOriginFromHeaders(headerList);
    if (!origin) {
      console.error(
        "Product metadata: could not resolve app origin (set NEXT_PUBLIC_APP_URL).",
      );
      return { kind: "uncertain", displayName: humanizeSlug(slug) };
    }

    const cookie = headerList.get("cookie");

    const response = await fetch(`${origin}/api/products/${slug}`, {
      headers: cookie ? { Cookie: cookie } : {},
      next: { revalidate: 60 },
    });

    if (response.status === 404) {
      return { kind: "not_found" };
    }

    if (!response.ok) {
      console.error(
        "Product metadata: API error",
        response.status,
        slug,
      );
      return { kind: "uncertain", displayName: humanizeSlug(slug) };
    }

    return { kind: "ok", product: (await response.json()) as ProductOverview };
  } catch (error) {
    console.error("Error fetching product data for metadata:", error);
    return { kind: "uncertain", displayName: humanizeSlug(slug) };
  }
}

function neutralProductMetadata(displayName: string, slug: string): Metadata {
  const description = `Privacy policy and terms of service analysis for ${displayName}.`;
  return {
    title: `${displayName} | Clausea AI`,
    description,
    openGraph: {
      title: `${displayName} | Clausea AI`,
      description,
      url: `${siteUrl}/products/${slug}`,
      siteName: "Clausea AI",
      images: [{ url: `${siteUrl}/og`, width: 1200, height: 630, alt: `${displayName}` }],
      locale: "en_US",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: `${displayName} | Clausea AI`,
      description,
      images: [`${siteUrl}/og`],
    },
    alternates: {
      canonical: `${siteUrl}/products/${slug}`,
    },
  };
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const result = await fetchProductForMetadata(slug);

  if (result.kind === "not_found") {
    return {
      title: "Product Not Found | Clausea AI",
      description: "The product you're looking for doesn't exist.",
      robots: {
        index: false,
        follow: false,
      },
    };
  }

  if (result.kind === "uncertain") {
    return neutralProductMetadata(result.displayName, slug);
  }

  const product = result.product;
  const productName = product.name || product.company_name || "Product";
  const description =
    product.one_line_summary ||
    `Privacy policy and terms of service analysis for ${productName}. Get insights into data collection, sharing practices, and user rights.`;

  // Create a risk description based on verdict
  const riskDescription =
    product.verdict === "very_user_friendly"
      ? "Very user-friendly privacy practices"
      : product.verdict === "user_friendly"
        ? "User-friendly privacy practices"
        : product.verdict === "moderate"
          ? "Moderate privacy concerns"
          : product.verdict === "pervasive"
            ? "Pervasive data collection practices"
            : product.verdict === "very_pervasive"
              ? "Very pervasive data collection practices"
              : "";

  const fullDescription = riskDescription
    ? `${description} ${riskDescription}.`
    : description;

  return {
    title: `${productName} - Privacy Policy Analysis | Clausea AI`,
    description: fullDescription,
    keywords: [
      `${productName} privacy policy`,
      `${productName} terms of service`,
      `${productName} data collection`,
      `${productName} privacy analysis`,
      "privacy policy analyzer",
      "legal document analysis",
    ],
    openGraph: {
      title: `${productName} - Privacy Policy Analysis | Clausea AI`,
      description: fullDescription,
      url: `${siteUrl}/products/${product.slug}`,
      siteName: "Clausea AI",
      images: [
        {
          url: `${siteUrl}/og`,
          width: 1200,
          height: 630,
          alt: `${productName} Privacy Analysis`,
        },
      ],
      locale: "en_US",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: `${productName} - Privacy Policy Analysis | Clausea AI`,
      description: fullDescription,
      images: [`${siteUrl}/og`],
    },
    alternates: {
      canonical: `${siteUrl}/products/${product.slug}`,
    },
  };
}

export default async function ProductLayout({
  children,
}: {
  children: React.ReactNode;
  params: Promise<{ slug: string }>;
}) {
  return <>{children}</>;
}
