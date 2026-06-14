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
