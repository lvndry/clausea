import { describe, expect, it } from "vitest";

import {
  deriveProductPageOverviewState,
  isProductNotFound,
} from "./product-page-fetch-state";

describe("deriveProductPageOverviewState", () => {
  it("returns ready when overview request succeeds", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: true,
      overviewStatus: 200,
      explainerStatus: 429,
      topicsStatus: 429,
    });

    expect(result).toBe("ready");
  });

  it("returns unauthorized when overview returns 401", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: false,
      overviewStatus: 401,
      explainerStatus: 200,
      topicsStatus: 200,
    });

    expect(result).toBe("unauthorized");
  });

  it("returns limit_reached when overview returns 429", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: false,
      overviewStatus: 429,
      explainerStatus: 200,
      topicsStatus: 200,
    });

    expect(result).toBe("limit_reached");
  });

  it("returns limit_reached when explainer or topics return 429", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: false,
      overviewStatus: 503,
      explainerStatus: 429,
      topicsStatus: 200,
    });

    expect(result).toBe("limit_reached");
  });

  it("returns server_error for 5xx responses", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: false,
      overviewStatus: 500,
      explainerStatus: 200,
      topicsStatus: 200,
      productStatus: 200,
    });

    expect(result).toBe("server_error");
  });

  it("returns thin_evidence when overview returns 424 with thin_evidence code", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: false,
      overviewStatus: 424,
      explainerStatus: 425,
      topicsStatus: 425,
      overviewPayload: {
        detail: {
          code: "thin_evidence",
          message: "Not enough policy documents",
        },
      },
    });

    expect(result).toBe("thin_evidence");
  });

  it("returns indexing for non-limit overview misses like 425", () => {
    const result = deriveProductPageOverviewState({
      overviewOk: false,
      overviewStatus: 425,
      explainerStatus: 425,
      topicsStatus: 425,
    });

    expect(result).toBe("indexing");
  });
});

describe("isProductNotFound", () => {
  it("returns true only for HTTP 404", () => {
    expect(isProductNotFound(404)).toBe(true);
    expect(isProductNotFound(500)).toBe(false);
    expect(isProductNotFound(429)).toBe(false);
  });
});
