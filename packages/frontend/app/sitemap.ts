import type { MetadataRoute } from "next";

import { getBackendUrl } from "@lib/config";

const siteUrl = process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co";

interface SitemapProduct {
  slug: string;
  last_modified?: string | null;
}

// Analyzed products only — unanalyzed pages are placeholder content, not worth indexing.
async function getAnalyzedProducts(): Promise<SitemapProduct[]> {
  try {
    const response = await fetch(getBackendUrl("/products/sitemap"), {
      next: { revalidate: 3600 },
    });
    if (!response.ok) {
      console.warn("Failed to fetch products for sitemap");
      return [];
    }
    const products = await response.json();
    return Array.isArray(products) ? products : [];
  } catch (error) {
    console.warn("Error fetching products for sitemap:", error);
    return [];
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = siteUrl.replace(/\/$/, "");
  const now = new Date();

  // Static pages with more accurate lastModified dates
  const staticPages: MetadataRoute.Sitemap = [
    {
      url: baseUrl,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 1.0,
    },
    {
      url: `${baseUrl}/features`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/pricing`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/products`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${baseUrl}/contact`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.5,
    },
    {
      url: `${baseUrl}/privacy`,
      lastModified: new Date("2026-01-02"), // Update when privacy policy changes
      changeFrequency: "yearly",
      priority: 0.3,
    },
    {
      url: `${baseUrl}/terms`,
      lastModified: new Date("2026-01-02"), // Update when terms change
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];

  // Dynamic product pages (analyzed products only)
  const products = await getAnalyzedProducts();
  const productPages: MetadataRoute.Sitemap = products
    .filter((product) => product.slug)
    .map((product) => {
      // An Invalid Date would throw during serialization and 500 the whole sitemap.
      const parsed = product.last_modified
        ? new Date(product.last_modified)
        : null;
      const lastModified =
        parsed && !Number.isNaN(parsed.getTime()) ? parsed : now;
      return {
        url: `${baseUrl}/products/${product.slug}`,
        lastModified,
        changeFrequency: "weekly" as const,
        priority: 0.7,
      };
    });

  return [...staticPages, ...productPages];
}
