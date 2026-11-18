// The static site does not load plans from the API, and the upgrade button
// always hands over to the app, which knows the real prices.
export function useProPricing() {
  return {
    priceIds: { monthly: "", annual: "" },
    loaded: true,
    getProPriceId: (_interval: "monthly" | "annual") => "app",
    isProCheckoutAvailable: (_interval: "monthly" | "annual") => true,
    getCheckoutUnavailableMessage: (_interval: "monthly" | "annual") =>
      null as string | null,
  };
}
