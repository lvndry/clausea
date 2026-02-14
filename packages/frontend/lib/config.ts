// Backend URL helpers
export function getBackendUrl(path: string = "") {
  let baseUrl = process.env.BACKEND_BASE_URL || "http://localhost:8000";

  baseUrl = baseUrl.replace(/\/$/, "");

  const cleanPath = path.replace(/^\//, "");
  return `${baseUrl}/${cleanPath}`;
}

export const apiEndpoints = {
  tierLimits: () => getBackendUrl("/users/tier-limits"),
  documents: () => getBackendUrl("/documents"),
  analysis: () => getBackendUrl("/analysis"),
  conversations: () => getBackendUrl("/conversations"),
  products: () => getBackendUrl("/products"),
  q: () => getBackendUrl("/q"),
  users: () => getBackendUrl("/users"),
  metaSummary: (slug: string) => getBackendUrl(`/products/${slug}/overview`),
} as const;

// Application configuration
export const config = {
  // App configuration
  app: {
    name: "Clausea",
    version: "1.0.0",
    url: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
    environment: process.env.NODE_ENV || "development",
  },

  // Backend configuration
  backend: {
    baseUrl: process.env.BACKEND_BASE_URL || "http://localhost:8000",
    timeout: 30000, // 30 seconds
    retries: 3,
  },

  // Authentication configuration
  auth: {
    signInUrl: process.env.NEXT_PUBLIC_CLERK_SIGN_IN_URL || "/sign-in",
    signUpUrl: process.env.NEXT_PUBLIC_CLERK_SIGN_UP_URL || "/sign-up",
    afterSignInUrl:
      process.env.NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL || "/products",
    afterSignUpUrl:
      process.env.NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL || "/products",
  },
} as const;
