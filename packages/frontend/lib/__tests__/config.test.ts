import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiEndpoints, getBackendUrl } from "../config";

describe("getBackendUrl", () => {
  const originalEnv = process.env.BACKEND_BASE_URL;

  beforeEach(() => {
    delete process.env.BACKEND_BASE_URL;
  });

  afterEach(() => {
    if (originalEnv !== undefined) {
      process.env.BACKEND_BASE_URL = originalEnv;
    } else {
      delete process.env.BACKEND_BASE_URL;
    }
  });

  it("uses default localhost when no env var is set", () => {
    const url = getBackendUrl("/test");
    expect(url).toBe("http://localhost:8000/test");
  });

  it("handles empty path", () => {
    const url = getBackendUrl("");
    expect(url).toBe("http://localhost:8000/");
  });

  it("handles path without leading slash", () => {
    const url = getBackendUrl("products");
    expect(url).toBe("http://localhost:8000/products");
  });

  it("handles path with leading slash", () => {
    const url = getBackendUrl("/products");
    expect(url).toBe("http://localhost:8000/products");
  });

  it("strips trailing slash from base URL", () => {
    process.env.BACKEND_BASE_URL = "https://api.clausea.co/";
    // Need to re-import to pick up new env
    // Since getBackendUrl reads env at call time, this works
    const url = getBackendUrl("/test");
    expect(url).toBe("https://api.clausea.co/test");
  });

  it("handles default path parameter", () => {
    const url = getBackendUrl();
    expect(url).toBe("http://localhost:8000/");
  });
});

describe("apiEndpoints", () => {
  it("tierLimits returns correct URL", () => {
    expect(apiEndpoints.tierLimits()).toContain("/users/tier-limits");
  });

  it("products returns correct URL", () => {
    expect(apiEndpoints.products()).toContain("/products");
  });

  it("conversations returns correct URL", () => {
    expect(apiEndpoints.conversations()).toContain("/conversations");
  });

  it("users returns correct URL", () => {
    expect(apiEndpoints.users()).toContain("/users");
  });

  it("metaSummary includes slug", () => {
    const url = apiEndpoints.metaSummary("test-product");
    expect(url).toContain("/products/test-product/overview");
  });

  it("q returns correct URL", () => {
    expect(apiEndpoints.q()).toContain("/q");
  });
});
