import type { Metadata } from "next";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

export const metadata: Metadata = {
  title: "Privacy Policy - How We Protect Your Data | Clausea AI",
  description:
    "Read Clausea AI's Privacy Policy to understand how we collect, use, and protect your information. We're committed to your privacy and data security.",
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "Privacy Policy - How We Protect Your Data | Clausea AI",
    description:
      "Read Clausea AI's Privacy Policy to understand how we collect, use, and protect your information.",
    url: `${siteUrl}/privacy`,
    siteName: "Clausea AI",
    images: [
      {
        url: `${siteUrl}/og`,
        width: 1200,
        height: 630,
        alt: "Clausea AI Privacy Policy",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  alternates: {
    canonical: `${siteUrl}/privacy`,
  },
};

export default function PrivacyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
