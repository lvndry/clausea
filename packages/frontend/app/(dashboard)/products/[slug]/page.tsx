import { getBackendUrl } from "@lib/config";
import type { Product } from "@/types";

import CompanyPage from "./product-page-client";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function fetchPublic(url: string): Promise<any> {
  try {
    const res = await fetch(url, { next: { revalidate: 300 } });
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

  const [initialProduct, initialData, initialDocuments] = await Promise.all([
    fetchPublic(getBackendUrl(`/products/${slug}`)),
    fetchPublic(getBackendUrl(`/products/${slug}/overview`)),
    fetchPublic(getBackendUrl(`/products/${slug}/documents`)),
  ]);

  return (
    <CompanyPage
      initialProduct={initialProduct as Product | null}
      initialData={initialData}
      initialDocuments={initialDocuments ?? []}
    />
  );
}
