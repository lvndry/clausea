import type { Metadata } from "next";

import { ProductStructuredData } from "@/components/seo/structured-data";

import {
  type ProductMetadata,
  fetchProductForMetadata,
  humanizeSlug,
} from "./product-page-server";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

function buildOgUrl(
  base: string,
  name: string,
  grade?: ProductMetadata["grade"],
  verdict?: string | null,
): string {
  const params = new URLSearchParams({ name });
  if (grade) params.set("grade", grade);
  if (verdict) params.set("verdict", verdict);
  return `${base}/og?${params.toString()}`;
}

function neutralProductMetadata(displayName: string, slug: string): Metadata {
  const description = `Policy overview for ${displayName} — data practices, terms, and risks from crawled documents.`;
  return {
    title: `${displayName} | Clausea AI`,
    description,
    openGraph: {
      title: `${displayName} | Clausea AI`,
      description,
      url: `${siteUrl}/products/${slug}`,
      siteName: "Clausea AI",
      images: [
        {
          url: buildOgUrl(siteUrl, displayName),
          width: 1200,
          height: 630,
          alt: `${displayName}`,
        },
      ],
      locale: "en_US",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: `${displayName} | Clausea AI`,
      description,
      images: [buildOgUrl(siteUrl, displayName)],
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
    `Policy overview for ${productName} — data collection, sharing, terms, and user-facing risks from analyzed documents.`;

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
    title: `${productName} - Policy overview | Clausea AI`,
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
      title: `${productName} - Policy overview | Clausea AI`,
      description: fullDescription,
      url: `${siteUrl}/products/${product.slug}`,
      siteName: "Clausea AI",
      images: [
        {
          url: buildOgUrl(siteUrl, productName, product.grade, product.verdict),
          width: 1200,
          height: 630,
          alt: `${productName} policy overview`,
        },
      ],
      locale: "en_US",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: `${productName} - Policy overview | Clausea AI`,
      description: fullDescription,
      images: [
        buildOgUrl(siteUrl, productName, product.grade, product.verdict),
      ],
    },
    alternates: {
      canonical: `${siteUrl}/products/${product.slug}`,
    },
  };
}

export default async function ProductLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const result = await fetchProductForMetadata(slug);

  const product = result.kind === "ok" ? result.product : null;
  const productName = product?.name || product?.company_name || null;
  const description = product?.one_line_summary || undefined;

  return (
    <>
      {product && productName && (
        <>
          <ProductStructuredData
            siteUrl={siteUrl}
            productName={productName}
            productSlug={product.slug}
            description={description}
            companyName={product.company_name || undefined}
          />
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{
              __html: JSON.stringify({
                "@context": "https://schema.org",
                "@type": "WebPage",
                name: `${productName} Privacy Policy Analysis`,
                description:
                  description ||
                  `Privacy policy and terms of service analysis for ${productName}`,
                url: `${siteUrl}/products/${product.slug}`,
                isPartOf: { "@id": siteUrl },
                about: {
                  "@type": "SoftwareApplication",
                  name: productName,
                  ...(product.company_name
                    ? {
                        brand: { "@type": "Brand", name: product.company_name },
                      }
                    : {}),
                },
                ...(typeof product.grade === "string" && product.grade
                  ? {
                      review: {
                        "@type": "Review",
                        reviewAspect: "Privacy & Data Practices",
                        reviewRating: {
                          "@type": "Rating",
                          ratingValue: String(product.grade),
                          bestRating: "E",
                          worstRating: "A",
                          description:
                            product.verdict === "very_user_friendly"
                              ? "Very user-friendly"
                              : product.verdict === "user_friendly"
                                ? "User-friendly"
                                : product.verdict === "moderate"
                                  ? "Moderate concerns"
                                  : product.verdict === "pervasive"
                                    ? "Pervasive data collection"
                                    : "Very pervasive data collection",
                        },
                        author: {
                          "@type": "Organization",
                          name: "Clausea AI",
                          url: siteUrl,
                        },
                      },
                    }
                  : {}),
              }),
            }}
          />
        </>
      )}
      {children}
    </>
  );
}
