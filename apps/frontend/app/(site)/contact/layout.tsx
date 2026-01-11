import type { Metadata } from "next";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

export const metadata: Metadata = {
  title: "Contact Us - Get in Touch | Clausea AI",
  description:
    "Have questions about Clausea AI? Contact our team for enterprise features, support, or general inquiries. We're here to help with your legal document analysis needs.",
  keywords: [
    "contact Clausea AI",
    "legal document analysis support",
    "enterprise legal AI contact",
  ],
  openGraph: {
    title: "Contact Us - Get in Touch | Clausea AI",
    description:
      "Have questions about Clausea AI? Contact our team for enterprise features, support, or general inquiries.",
    url: `${siteUrl}/contact`,
    siteName: "Clausea AI",
    images: [
      {
        url: `${siteUrl}/og`,
        width: 1200,
        height: 630,
        alt: "Contact Clausea AI",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Contact Us - Get in Touch | Clausea AI",
    description:
      "Have questions about Clausea AI? Contact our team for enterprise features, support, or general inquiries.",
    images: [`${siteUrl}/og`],
  },
  alternates: {
    canonical: `${siteUrl}/contact`,
  },
};

export default function ContactLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
