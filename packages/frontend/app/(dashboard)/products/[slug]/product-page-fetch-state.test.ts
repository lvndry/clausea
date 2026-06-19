import { describe, expect, it } from "vitest";

import { deriveProductPageOverviewState } from "./product-page-fetch-state";

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
