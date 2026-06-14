"use server";

import { revalidateTag } from "next/cache";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function subscribeIndexationNotify(
  slug: string,
  email: string,
): Promise<void> {
  await httpJson(`${apiEndpoints.products()}/${slug}/indexation-notify`, {
    method: "POST",
    body: { email },
  });
}

export async function revalidateProduct(slug: string): Promise<void> {
  revalidateTag(`product-${slug}`, "max");
}
