import type { Metadata } from "next";

import { getBackendUrl } from "@lib/config";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

interface ProductOverview {
  product_name: string;
  product_slug: string;
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

async function getProductData(slug: string): Promise<ProductOverview | null> {
  try {
    const backendUrl = getBackendUrl(`/products/${slug}`);
    const response = await fetch(backendUrl, {
      next: { revalidate: 3600 }, // Revalidate every hour
    });

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching product data for metadata:", error);
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const product = await getProductData(slug);

  if (!product) {
    return {
      title: "Product Not Found | Clausea AI",
      description: "The product you're looking for doesn't exist.",
      robots: {
        index: false,
        follow: false,
      },
    };
  }

  const productName = product.product_name || product.company_name || "Product";
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
      url: `${siteUrl}/products/${product.product_slug}`,
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
      canonical: `${siteUrl}/products/${product.product_slug}`,
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
