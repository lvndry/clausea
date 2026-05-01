import { auth } from "@clerk/nextjs/server";

import { getBackendUrl } from "@lib/config";
import type { Product } from "@/types";

import CompanyPage, { type DocumentSummary, type ProductOverview } from "./product-page-client";

async function fetchWithAuth(url: string, headers: HeadersInit): Promise<unknown> {
  try {
    const res = await fetch(url, { headers });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  const { getToken } = await auth();
  const token = await getToken();
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

  const [initialProduct, initialData, initialDocuments] = await Promise.all([
    fetchWithAuth(getBackendUrl(`/products/${slug}`), headers),
    fetchWithAuth(getBackendUrl(`/products/${slug}/overview`), headers),
    fetchWithAuth(getBackendUrl(`/products/${slug}/documents`), headers),
  ]);

  return (
    <CompanyPage
      initialProduct={initialProduct as Product | null}
      initialData={initialData as ProductOverview | null}
      initialDocuments={(initialDocuments as DocumentSummary[]) ?? []}
    />
  );
}
