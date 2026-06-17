import { auth } from "@clerk/nextjs/server";
import { getBackendUrl } from "@lib/config";
import { enrichLogos } from "@lib/logo";

import {
  ProductsListClient,
  type ProductsPage,
} from "./products-list-client";

const EMPTY_PAGE: ProductsPage = { items: [], total: 0, page: 1, pages: 1 };

async function fetchInitialProducts(page: number): Promise<ProductsPage> {
  try {
    const { getToken } = await auth();
    const token = await getToken();
    const params = new URLSearchParams({ page: String(page), limit: "20" });
    const res = await fetch(getBackendUrl(`/products?${params.toString()}`), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return EMPTY_PAGE;
    return enrichLogos((await res.json()) as ProductsPage);
  } catch {
    return EMPTY_PAGE;
  }
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page } = await searchParams;
  const parsed = page ? Number.parseInt(page, 10) : 1;
  const initialData = await fetchInitialProducts(
    Number.isFinite(parsed) && parsed > 0 ? parsed : 1,
  );

  return <ProductsListClient initialData={initialData} />;
}
