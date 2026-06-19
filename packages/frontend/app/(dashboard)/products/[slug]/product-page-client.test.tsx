import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ReactNode } from "react";

import { render, screen, waitFor } from "@testing-library/react";

import CompanyPage from "./product-page-client";

vi.mock("next/navigation", () => ({
  useParams: () => ({ slug: "acme-inc" }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("posthog-js", () => ({
  default: {
    capture: vi.fn(),
  },
}));

vi.mock("@/app/actions/pipeline", () => ({
  triggerPipeline: vi.fn(),
}));

vi.mock("@/app/actions/products", () => ({
  subscribeIndexationNotify: vi.fn(),
}));

function createJsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function getRequestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }

  if (input instanceof URL) {
    return input.toString();
  }

  return input.url;
}

describe("CompanyPage limit reached state", () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = getRequestUrl(input);

    if (url.endsWith("/api/products/acme-inc")) {
      return createJsonResponse(429, { error: "rate_limited" });
    }
    if (url.endsWith("/api/products/acme-inc/documents")) {
      return createJsonResponse(200, []);
    }
    if (url.endsWith("/api/products/acme-inc/overview")) {
      return createJsonResponse(429, { error: "rate_limited" });
    }
    if (url.endsWith("/api/products/acme-inc/explainer")) {
      return createJsonResponse(429, { error: "rate_limited" });
    }
    if (url.endsWith("/api/products/acme-inc/topics")) {
      return createJsonResponse(429, { error: "rate_limited" });
    }

    return createJsonResponse(500, { error: `Unexpected URL: ${url}` });
  });

  beforeEach(() => {
    fetchMock.mockClear();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders limit reached UI when product is missing", async () => {
    render(<CompanyPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", {
          name: "Acme Inc",
        }),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Usage Limit Reached")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "Product Not Found",
      }),
    ).not.toBeInTheDocument();

    const pipelineFetchCalled = fetchMock.mock.calls.some(([input]) =>
      getRequestUrl(input).includes("/api/pipeline/"),
    );
    expect(pipelineFetchCalled).toBe(false);
  });
});
