import { describe, expect, it } from "vitest";

import { AUTH_ROUTES, getSignedInDestination } from "@/lib/auth-routes";

describe("getSignedInDestination", () => {
  it("routes completed users to products", () => {
    expect(getSignedInDestination(true)).toBe(AUTH_ROUTES.products);
  });

  it("routes incomplete users to onboarding", () => {
    expect(getSignedInDestination(false)).toBe(AUTH_ROUTES.onboarding);
    expect(getSignedInDestination(undefined)).toBe(AUTH_ROUTES.onboarding);
  });
});
