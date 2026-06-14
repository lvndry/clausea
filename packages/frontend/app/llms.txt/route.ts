const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

export function GET() {
  const body = `# Clausea

> Clausea is an AI platform that reads privacy policies and terms of service and explains, in plain English, how a digital service treats your data — ending in a clear low-to-high risk verdict for each service.

## Core pages
- [Home](${siteUrl}/): What Clausea does
- [Features](${siteUrl}/features): How the analysis works
- [Pricing](${siteUrl}/pricing): Plans
- [Privacy Policy](${siteUrl}/privacy)
- [Terms of Service](${siteUrl}/terms)
- [Cookie Policy](${siteUrl}/cookie-policy)

## Service analyses
Per-service privacy & terms breakdowns live at ${siteUrl}/products/{slug}. Each service also exposes a machine-readable plain-text summary at ${siteUrl}/api/products/{slug}/summary.txt. The full list of analyzed services is in the sitemap at ${siteUrl}/sitemap.xml.
`;

  return new Response(body, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Cache-Control": "public, max-age=0, s-maxage=86400",
    },
  });
}
