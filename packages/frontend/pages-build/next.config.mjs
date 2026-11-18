import { fileURLToPath } from "node:url";

const basePath = "/clausea";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  basePath,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url)),
    resolveAlias: {
      "@clerk/nextjs": "./pages-stubs/clerk.tsx",
      "@clerk/ui": "./pages-stubs/clerk-ui.ts",
      "posthog-js": "./pages-stubs/posthog.ts",
    },
  },
};

export default nextConfig;
