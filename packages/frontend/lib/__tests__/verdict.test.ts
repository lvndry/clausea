import { describe, expect, it } from "vitest";

import { getVerdictConfig } from "../verdict";

describe("getVerdictConfig", () => {
  it("returns correct config for very_user_friendly", () => {
    const config = getVerdictConfig("very_user_friendly");
    expect(config.label).toBe("Very User Friendly");
    expect(config.variant).toBe("success");
    expect(config.description).toBe("Excellent privacy practices");
    expect(config.cardColor).toContain("green");
    expect(config.overviewColor).toContain("green");
  });

  it("returns correct config for user_friendly", () => {
    const config = getVerdictConfig("user_friendly");
    expect(config.label).toBe("User Friendly");
    expect(config.variant).toBe("success");
    expect(config.description).toBe("Good privacy practices");
  });

  it("returns correct config for moderate", () => {
    const config = getVerdictConfig("moderate");
    expect(config.label).toBe("Moderate");
    expect(config.variant).toBe("warning");
    expect(config.description).toBe("Standard privacy practices");
    expect(config.cardColor).toContain("amber");
  });

  it("returns correct config for pervasive", () => {
    const config = getVerdictConfig("pervasive");
    expect(config.label).toBe("Pervasive");
    expect(config.variant).toBe("warning");
    expect(config.description).toBe("Concerning privacy practices");
    expect(config.cardColor).toContain("orange");
  });

  it("returns correct config for very_pervasive", () => {
    const config = getVerdictConfig("very_pervasive");
    expect(config.label).toBe("Very Pervasive");
    expect(config.variant).toBe("danger");
    expect(config.description).toBe("Very concerning privacy practices");
    expect(config.cardColor).toContain("red");
  });

  it("returns default config for unknown verdict", () => {
    const config = getVerdictConfig("unknown_value");
    expect(config.label).toBe("Unknown");
    expect(config.variant).toBe("secondary");
    expect(config.description).toBe("Analysis pending");
  });

  it("returns default config for empty string", () => {
    const config = getVerdictConfig("");
    expect(config.label).toBe("Unknown");
    expect(config.variant).toBe("secondary");
  });

  // Ensure all configs have required fields
  it.each([
    "very_user_friendly",
    "user_friendly",
    "moderate",
    "pervasive",
    "very_pervasive",
    "unknown",
  ])("config for '%s' has all required fields", (verdict) => {
    const config = getVerdictConfig(verdict);
    expect(config).toHaveProperty("label");
    expect(config).toHaveProperty("description");
    expect(config).toHaveProperty("variant");
    expect(config).toHaveProperty("cardIcon");
    expect(config).toHaveProperty("cardColor");
    expect(config).toHaveProperty("cardBg");
    expect(config).toHaveProperty("overviewIcon");
    expect(config).toHaveProperty("overviewColor");
    expect(config).toHaveProperty("overviewBg");
  });
});
