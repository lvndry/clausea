import type { MetadataRoute } from "next";

const siteUrl = process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co";

export default function robots(): MetadataRoute.Robots {
  const baseUrl = siteUrl.replace(/\/$/, "");

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/dashboard/", "/c/", "/checkout/", "/onboarding/"],
      },
      // Explicitly allow AI crawlers used by LLMs / answer engines (GEO)
      {
        userAgent: [
          "GPTBot",
          "ChatGPT-User",
          "ClaudeBot",
          "anthropic-ai",
          "PerplexityBot",
          "Applebot-Extended",
          "cohere-ai",
          "Omgilibot",
        ],
        allow: ["/", "/products/"],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  };
}
