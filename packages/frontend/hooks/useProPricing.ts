"use client";

import { useEffect, useMemo, useState } from "react";

import {
  type BillingInterval,
  type ProPriceIds,
  getProCheckoutUnavailableMessage,
  getProPriceIdFrom,
  isProCheckoutAvailableFrom,
  resolveProPriceIds,
} from "@/lib/pricing";

interface PlansResponse {
  pro_monthly: string;
  pro_annual: string;
}

export function useProPricing() {
  const [runtimeIds, setRuntimeIds] = useState<Partial<ProPriceIds> | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadPlans() {
      try {
        const response = await fetch("/api/subscriptions/plans");
        if (!response.ok) {
          return;
        }

        const data = (await response.json()) as PlansResponse;
        if (cancelled) {
          return;
        }

        setRuntimeIds({
          monthly: data.pro_monthly || undefined,
          annual: data.pro_annual || undefined,
        });
      } catch {
        // Keep build-time fallbacks from pricing.ts
      } finally {
        if (!cancelled) {
          setLoaded(true);
        }
      }
    }

    void loadPlans();

    return () => {
      cancelled = true;
    };
  }, []);

  const priceIds = useMemo(
    () => resolveProPriceIds(runtimeIds ?? undefined),
    [runtimeIds],
  );

  const getProPriceId = (interval: BillingInterval) =>
    getProPriceIdFrom(priceIds, interval);

  const isProCheckoutAvailable = (interval: BillingInterval) =>
    isProCheckoutAvailableFrom(priceIds, interval);

  const getCheckoutUnavailableMessage = (interval: BillingInterval) =>
    getProCheckoutUnavailableMessage(interval, priceIds);

  return {
    priceIds,
    loaded,
    getProPriceId,
    isProCheckoutAvailable,
    getCheckoutUnavailableMessage,
  };
}
