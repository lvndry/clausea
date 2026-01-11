import type { MetadataRoute } from "next";

import { getBackendUrl } from "@lib/config";

const siteUrl = process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co";

interface Product {
  slug: string;
  name: string;
  updated_at?: string;
}

async function getProducts(): Promise<Product[]> {
  try {
    const backendUrl = getBackendUrl("/products");
    const response = await fetch(backendUrl, {
      next: { revalidate: 3600 }, // Revalidate every hour
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

  // Dynamic product pages
  const products = await getProducts();
  const productPages: MetadataRoute.Sitemap = products.map((product) => ({
    url: `${baseUrl}/products/${product.slug}`,
    lastModified: product.updated_at
      ? new Date(product.updated_at)
      : new Date(),
    changeFrequency: "weekly" as const,
    priority: 0.7,
  }));

  return [...staticPages, ...productPages];
}
