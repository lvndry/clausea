import type { Viewport } from "next";
import { Fraunces, Inter, Plus_Jakarta_Sans } from "next/font/google";

import {
  OrganizationStructuredData,
  SoftwareApplicationStructuredData,
  WebsiteStructuredData,
} from "@/components/seo/structured-data";

import "./globals.css";
import { Provider } from "./provider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
});

const siteUrl = (
  process.env.NEXT_PUBLIC_APP_URL || "https://clausea.co"
).replace(/\/$/, "");

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f6" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1918" },
  ],
};

export const metadata = {
  metadataBase: new URL(siteUrl),
  title: "Clausea AI - Privacy Policies & Terms, Made Easy",
  description:
    "Navigate legal complexities with AI precision. Understand privacy policies, terms of service, cookie policies, and other legal agreements instantly.",
  keywords: [
    "legal document analysis",
    "AI legal assistant",
    "privacy policy analyzer",
    "terms of service analyzer",
    "contract analysis",
    "legal document intelligence",
    "cookie policy analysis",
    "GDPR compliance",
    "CCPA compliance",
    "legal AI",
    "ai",
    "llm",
    "ai agents",
    "semantic search",
    "terms of service",
    "privacy policy",
  ],
  authors: [{ name: "Clausea AI" }],
  creator: "Clausea AI",
  publisher: "Clausea AI",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: siteUrl,
    siteName: "Clausea AI",
    title: "Clausea AI - Privacy Policies & Terms, Made Easy",
    description:
      "Navigate legal complexities with ease. Understand privacy policies, terms of service, cookie policies, and other legal agreements instantly.",
    images: [
      {
        url: `${siteUrl}/og`,
        width: 1200,
        height: 630,
        alt: "Clausea AI - Legal Document Intelligence Platform",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Clausea AI - Privacy Policies & Terms, Made Easy",
    description:
      "Navigate legal complexities with AI precision. Understand privacy policies, terms of service, cookie policies, and other legal agreements instantly.",
    images: [`${siteUrl}/og`],
    creator: "@clauseaai",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  alternates: {
    canonical: siteUrl,
  },
};

export default function Layout(props: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jakarta.variable} ${fraunces.variable} scroll-smooth`}
      suppressHydrationWarning
    >
      <head>
        {/* Favicons */}
        <link
          rel="apple-touch-icon"
          sizes="76x76"
          href="/static/favicons/apple-touch-icon.png"
        />
        <link
          rel="icon"
          type="image/png"
          sizes="32x32"
          href="/static/favicons/favicon-32x32.png"
        />
        <link
          rel="icon"
          type="image/png"
          sizes="16x16"
          href="/static/favicons/favicon-16x16.png"
        />
        {/* Verification tags - Add these in your environment variables */}
        {process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION && (
          <meta
            name="google-site-verification"
            content={process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION}
          />
        )}
        {process.env.NEXT_PUBLIC_BING_VERIFICATION && (
          <meta
            name="msvalidate.01"
            content={process.env.NEXT_PUBLIC_BING_VERIFICATION}
          />
        )}
        {/* Structured Data */}
        <OrganizationStructuredData siteUrl={siteUrl} />
        <WebsiteStructuredData siteUrl={siteUrl} />
        <SoftwareApplicationStructuredData siteUrl={siteUrl} />
      </head>
      <body className="antialiased selection:bg-secondary/30">
        <div className="noise-overlay" />
        <Provider>{props.children}</Provider>
      </body>
    </html>
  );
}
