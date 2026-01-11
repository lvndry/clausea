/**
 * Structured Data (JSON-LD) component for SEO
 * Provides schema.org markup for better search engine understanding
 */

interface OrganizationStructuredDataProps {
  siteUrl: string;
}

export function OrganizationStructuredData({
  siteUrl,
}: OrganizationStructuredDataProps) {
  const organizationSchema = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "Clausea AI",
    url: siteUrl,
    logo: `${siteUrl}/static/favicons/logo.png`,
    description:
      "Navigate legal complexities with AI precision. Summarize, analyze and ask questions to dense legal documents instantly.",
    sameAs: [
      "https://twitter.com/clauseaai",
      // Add other social media profiles here
    ],
    contactPoint: {
      "@type": "ContactPoint",
      contactType: "Customer Service",
      email: "contact@clausea.co",
    },
    address: {
      "@type": "PostalAddress",
      addressLocality: "Paris",
      addressCountry: "FR",
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
    />
  );
}

interface WebsiteStructuredDataProps {
  siteUrl: string;
}

export function WebsiteStructuredData({ siteUrl }: WebsiteStructuredDataProps) {
  const websiteSchema = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Clausea AI",
    url: siteUrl,
    description:
      "Navigate legal complexities with AI precision. Summarize, analyze and ask questions to dense legal documents instantly.",
    potentialAction: {
      "@type": "SearchAction",
      target: {
        "@type": "EntryPoint",
        urlTemplate: `${siteUrl}/search?q={search_term_string}`,
      },
      "query-input": "required name=search_term_string",
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
    />
  );
}

interface SoftwareApplicationStructuredDataProps {
  siteUrl: string;
}

export function SoftwareApplicationStructuredData({
  siteUrl,
}: SoftwareApplicationStructuredDataProps) {
  const softwareSchema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Clausea AI",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
    },
    description:
      "AI-powered legal document analysis platform that helps users understand, analyze, and compare legal documents such as privacy policies, terms of service, and contracts.",
    featureList: [
      "Document upload and processing",
      "AI-powered summarization and analysis",
      "Semantic search and clause comparison",
      "Risk assessment and compliance checking",
      "API access for developers",
    ],
    aggregateRating: {
      "@type": "AggregateRating",
      ratingValue: "4.8",
      ratingCount: "150",
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareSchema) }}
    />
  );
}

interface ProductStructuredDataProps {
  siteUrl: string;
  productName: string;
  productSlug: string;
  description?: string;
  companyName?: string;
}

export function ProductStructuredData({
  siteUrl,
  productName,
  productSlug,
  description,
  companyName,
}: ProductStructuredDataProps) {
  const productSchema = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: productName,
    description:
      description ||
      `Privacy policy and terms of service analysis for ${productName}`,
    url: `${siteUrl}/products/${productSlug}`,
    brand: {
      "@type": "Brand",
      name: companyName || productName,
    },
    category: "Legal Document Analysis",
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(productSchema) }}
    />
  );
}
