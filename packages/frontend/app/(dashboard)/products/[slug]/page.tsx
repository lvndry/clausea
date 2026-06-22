import { cookies } from "next/headers";

import type { ConsumerExplainer } from "@/components/dashboard/explainer/types";
import {
  PREVIEW_TOKEN_COOKIE,
  PREVIEW_TOKEN_HEADER,
} from "@/lib/preview-token";
import type {
  DocumentSummary,
  Product,
  ProductOverview,
  ProductTopicReport,
} from "@/types";
import { auth } from "@clerk/nextjs/server";
import { getBackendUrl } from "@lib/config";

import CompanyPage from "./product-page-client";

async function fetchWithAuth(
  url: string,
  headers: HeadersInit,
  tag: string,
): Promise<unknown> {
  try {
    const res = await fetch(url, {
      headers,
      next: { tags: [tag], revalidate: 3600 },
    });
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
  const cookieStore = await cookies();
  const previewToken = cookieStore.get(PREVIEW_TOKEN_COOKIE)?.value;
  const headers: HeadersInit = token
    ? { Authorization: `Bearer ${token}` }
    : previewToken
      ? { [PREVIEW_TOKEN_HEADER]: previewToken }
      : {};

  const tag = `product-${slug}`;
  const [
    initialProduct,
    initialData,
    initialDocuments,
    initialExplainer,
    initialTopics,
  ] = await Promise.all([
    fetchWithAuth(getBackendUrl(`/products/${slug}`), headers, tag),
    fetchWithAuth(getBackendUrl(`/products/${slug}/overview`), headers, tag),
    fetchWithAuth(getBackendUrl(`/products/${slug}/documents`), headers, tag),
    fetchWithAuth(getBackendUrl(`/products/${slug}/explainer`), headers, tag),
    fetchWithAuth(getBackendUrl(`/products/${slug}/topics`), headers, tag),
  ]);

  return (
    <CompanyPage
      key={slug}
      initialProduct={initialProduct as Product | null}
      initialData={initialData as ProductOverview | null}
      initialDocuments={(initialDocuments as DocumentSummary[]) ?? []}
      initialExplainer={initialExplainer as ConsumerExplainer | null}
      initialTopics={initialTopics as ProductTopicReport | null}
    />
  );
}
