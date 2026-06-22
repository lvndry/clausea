export const PRO_PRICE_MONTHLY = 9;
export const PRO_PRICE_ANNUAL = 100;

export const PRO_PRICE_ID_MONTHLY =
  process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO_MONTHLY ||
  process.env.NEXT_PUBLIC_PADDLE_PRICE_INDIVIDUAL_MONTHLY ||
  "";

export const PRO_PRICE_ID_ANNUAL =
  process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO_ANNUAL || "";

export type BillingInterval = "monthly" | "annual";

export interface ProPriceIds {
  monthly: string;
  annual: string;
}

export function resolveProPriceIds(
  override?: Partial<ProPriceIds>,
): ProPriceIds {
  return {
    monthly: override?.monthly || PRO_PRICE_ID_MONTHLY,
    annual: override?.annual || PRO_PRICE_ID_ANNUAL,
  };
}

export function getProPriceIdFrom(
  ids: ProPriceIds,
  interval: BillingInterval,
): string {
  return interval === "annual" ? ids.annual : ids.monthly;
}

export function isProCheckoutAvailableFrom(
  ids: ProPriceIds,
  interval: BillingInterval,
): boolean {
  return Boolean(getProPriceIdFrom(ids, interval));
}

export function getProPriceId(interval: BillingInterval): string {
  return getProPriceIdFrom(resolveProPriceIds(), interval);
}

export function getProDisplayPrice(interval: BillingInterval): {
  amount: number;
  suffix: string;
  label: string;
} {
  if (interval === "annual") {
    return {
      amount: PRO_PRICE_ANNUAL,
      suffix: "/yr",
      label: `$${PRO_PRICE_ANNUAL}/year`,
    };
  }

  return {
    amount: PRO_PRICE_MONTHLY,
    suffix: "/mo",
    label: `$${PRO_PRICE_MONTHLY}/month`,
  };
}

export function isAnnualCheckoutAvailable(): boolean {
  return Boolean(PRO_PRICE_ID_ANNUAL);
}

export function isProCheckoutAvailable(interval: BillingInterval): boolean {
  return isProCheckoutAvailableFrom(resolveProPriceIds(), interval);
}

export function getProCheckoutUnavailableMessage(
  interval: BillingInterval,
  ids: ProPriceIds = resolveProPriceIds(),
): string {
  if (interval === "annual" && !ids.annual && ids.monthly) {
    return "Annual billing is not available yet. Switch to monthly to upgrade.";
  }

  if (process.env.NODE_ENV === "development") {
    const envVar =
      interval === "annual"
        ? "NEXT_PUBLIC_PADDLE_PRICE_PRO_ANNUAL"
        : "NEXT_PUBLIC_PADDLE_PRICE_PRO_MONTHLY (or NEXT_PUBLIC_PADDLE_PRICE_INDIVIDUAL_MONTHLY)";
    return `Checkout is not configured. Set ${envVar} in .env.local and restart the dev server.`;
  }

  return "Upgrades are temporarily unavailable. Please contact support if this persists.";
}
