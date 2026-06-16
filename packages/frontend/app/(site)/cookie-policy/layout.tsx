import type { Metadata } from "next";

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

export const metadata: Metadata = {
  title: "Cookie Policy | Clausea AI",
  description:
    "Read Clausea AI's Cookie Policy to understand how we use cookies and similar technologies, and how you can control them.",
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "Cookie Policy | Clausea AI",
    description:
      "Read Clausea AI's Cookie Policy to understand how we use cookies and similar technologies.",
    url: `${siteUrl}/cookie-policy`,
    siteName: "Clausea AI",
    images: [
      {
        url: `${siteUrl}/og`,
        width: 1200,
        height: 630,
        alt: "Clausea AI Cookie Policy",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  alternates: {
    canonical: `${siteUrl}/cookie-policy`,
  },
};

export default function CookiePolicyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
