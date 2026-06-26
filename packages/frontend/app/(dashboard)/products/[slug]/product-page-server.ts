import { cookies } from "next/headers";

import { cache } from "react";

import type { ConsumerExplainer } from "@/components/dashboard/explainer/types";
import {
  PREVIEW_TOKEN_COOKIE,
  PREVIEW_TOKEN_HEADER,
} from "@/lib/preview-token";
import type { Product, ProductOverview } from "@/types";
import { auth } from "@clerk/nextjs/server";
import { getBackendUrl } from "@lib/config";

const REVALIDATE_SECONDS = 3600;

export interface ProductMetadata {
  name: string;
  slug: string;
  company_name?: string | null;
  one_line_summary?: string;
  grade?: ProductOverview["grade"];
  verdict?: ProductOverview["verdict"];
}

export type ProductMetadataFetch =
  | { kind: "ok"; product: ProductMetadata }
  | { kind: "not_found" }
  | { kind: "uncertain"; displayName: string };

export function humanizeSlug(slug: string): string {
  return slug
    .split(/[-_]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

async function fetchBackendJson<T>(
  path: string,
  headers: HeadersInit,
  tag: string,
): Promise<{ status: number; data: T | null }> {
  try {
    const res = await fetch(getBackendUrl(path), {
      headers,
      next: { tags: [tag], revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) {
      return { status: res.status, data: null };
    }
    return { status: res.status, data: (await res.json()) as T };
  } catch {
    return { status: 0, data: null };
  }
}

export const getProductRequestHeaders = cache(
  async (): Promise<HeadersInit> => {
    const { getToken } = await auth();
    const token = await getToken();
    const cookieStore = await cookies();
    const previewToken = cookieStore.get(PREVIEW_TOKEN_COOKIE)?.value;

    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
    if (previewToken) {
      return { [PREVIEW_TOKEN_HEADER]: previewToken };
    }
    return {};
  },
);

export const fetchProductRecord = cache(async (slug: string) => {
  const headers = await getProductRequestHeaders();
  return fetchBackendJson<Product>(
    `/products/${slug}`,
    headers,
    `product-${slug}`,
  );
});

export const fetchProductOverviewData = cache(
  async (slug: string): Promise<ProductOverview | null> => {
    const headers = await getProductRequestHeaders();
    const result = await fetchBackendJson<ProductOverview>(
      `/products/${slug}/overview`,
      headers,
      `product-${slug}`,
    );
    return result.data;
  },
);

export const fetchProductExplainerData = cache(
  async (slug: string): Promise<ConsumerExplainer | null> => {
    const headers = await getProductRequestHeaders();
    const result = await fetchBackendJson<ConsumerExplainer>(
      `/products/${slug}/explainer`,
      headers,
      `product-${slug}`,
    );
    return result.data;
  },
);

export const fetchProductPageShell = cache(async (slug: string) => {
  const [productResult, overview, explainer] = await Promise.all([
    fetchProductRecord(slug),
    fetchProductOverviewData(slug),
    fetchProductExplainerData(slug),
  ]);

  return {
    product: productResult.data,
    overview,
    explainer,
  };
});

/** Shared across layout metadata and page SSR — dedupes product + overview fetches. */
export const fetchProductForMetadata = cache(
  async (slug: string): Promise<ProductMetadataFetch> => {
    const [productResult, overview] = await Promise.all([
      fetchProductRecord(slug),
      fetchProductOverviewData(slug),
    ]);

    if (productResult.status === 404) {
      return { kind: "not_found" };
    }

    if (!productResult.data) {
      if (productResult.status > 0) {
        console.error(
          "Product metadata: backend error",
          productResult.status,
          slug,
        );
      }
      return { kind: "uncertain", displayName: humanizeSlug(slug) };
    }

    const product = productResult.data;

    return {
      kind: "ok",
      product: {
        name: product.name,
        slug: product.slug,
        company_name: product.company_name,
        one_line_summary: overview?.one_line_summary,
        grade: overview?.grade,
        verdict: overview?.verdict,
      },
    };
  },
);
