export const PRO_PRICE_MONTHLY = 9;
export const PRO_PRICE_ANNUAL = 100;

export const PRO_PRICE_ID_MONTHLY =
  process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO_MONTHLY ||
  process.env.NEXT_PUBLIC_PADDLE_PRICE_INDIVIDUAL_MONTHLY ||
  "";

export const PRO_PRICE_ID_ANNUAL =
  process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO_ANNUAL || "";

export type BillingInterval = "monthly" | "annual";

export function getProPriceId(interval: BillingInterval): string {
  return interval === "annual" ? PRO_PRICE_ID_ANNUAL : PRO_PRICE_ID_MONTHLY;
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
