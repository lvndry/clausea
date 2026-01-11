import type { Metadata } from "next";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

export const metadata: Metadata = {
  title: "Terms of Service - Legal Agreement | Clausea AI",
  description:
    "Read Clausea AI's Terms of Service to understand the legal agreement governing your use of our legal document analysis platform.",
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "Terms of Service - Legal Agreement | Clausea AI",
    description:
      "Read Clausea AI's Terms of Service to understand the legal agreement governing your use of our platform.",
    url: `${siteUrl}/terms`,
    siteName: "Clausea AI",
    images: [
      {
        url: `${siteUrl}/og`,
        width: 1200,
        height: 630,
        alt: "Clausea AI Terms of Service",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  alternates: {
    canonical: `${siteUrl}/terms`,
  },
};

export default function TermsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
