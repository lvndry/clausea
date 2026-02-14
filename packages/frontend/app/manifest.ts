import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Clausea AI - Legal Document Intelligence Platform",
    short_name: "Clausea AI",
    description:
      "Navigate legal complexities with AI precision. Summarize, analyze and ask questions to dense legal documents instantly.",
    start_url: "/",
    display: "standalone",
    background_color: "#faf8f4",
    theme_color: "#c6704f",
    orientation: "portrait-primary",
    scope: "/",
    icons: [
      {
        src: "/static/favicons/android-chrome-192x192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/static/favicons/android-chrome-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/static/favicons/apple-touch-icon.png",
        sizes: "180x180",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/static/favicons/favicon-32x32.png",
        sizes: "32x32",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/static/favicons/favicon-16x16.png",
        sizes: "16x16",
        type: "image/png",
        purpose: "any",
      },
    ],
    categories: ["business", "productivity", "legal"],
    lang: "en-US",
    dir: "ltr",
  };
}
