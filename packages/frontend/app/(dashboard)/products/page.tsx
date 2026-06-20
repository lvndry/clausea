import { getBackendUrl } from "@lib/config";
import { httpJson } from "@lib/http";
import { enrichLogos } from "@lib/logo";
import { productsPageSchema } from "@lib/schemas";

import { ProductsListClient, type ProductsPage } from "./products-list-client";

const EMPTY_PAGE: ProductsPage = { items: [], total: 0, page: 1, pages: 1 };

async function fetchInitialProducts(page: number): Promise<{
  data: ProductsPage;
  error: string | null;
}> {
  try {
    const params = new URLSearchParams({ page: String(page), limit: "20" });
    const data = await httpJson(
      getBackendUrl(`/products?${params.toString()}`),
      {
        method: "GET",
        schema: productsPageSchema,
      },
    );
    return { data: enrichLogos(data), error: null };
  } catch (err) {
    console.error("Failed to fetch initial products:", err);
    return {
      data: EMPTY_PAGE,
      error: err instanceof Error ? err.message : "Failed to fetch products",
    };
  }
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page } = await searchParams;
  const parsed = page ? Number.parseInt(page, 10) : 1;
  const { data: initialData, error: initialFetchError } =
    await fetchInitialProducts(
      Number.isFinite(parsed) && parsed > 0 ? parsed : 1,
    );

  return (
    <ProductsListClient
      initialData={initialData}
      initialFetchError={initialFetchError}
    />
  );
}
