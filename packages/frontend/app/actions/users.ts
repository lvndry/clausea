"use server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function upsertUser(input: {
  email?: string | null;
  first_name?: string | null;
  last_name?: string | null;
}): Promise<void> {
  await httpJson(apiEndpoints.users(), { method: "POST", body: input });
}

export async function completeOnboarding(): Promise<void> {
  await httpJson(`${apiEndpoints.users()}/complete-onboarding`, {
    method: "POST",
    body: { completed: true },
  });
}
