import { useEffect, useState } from "react";

import { TierLimitsResponse, getTierLimits } from "@lib/tier-api-client";

export function useTierLimits() {
  const [tierLimits, setTierLimits] = useState<TierLimitsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTierLimits() {
      try {
        setLoading(true);
        setError(null);
        const data = await getTierLimits();
        setTierLimits(data);
      } catch (err) {
        console.error("Failed to fetch tier limits:", err);
        setError(
          err instanceof Error ? err.message : "Failed to fetch tier limits",
        );
      } finally {
        setLoading(false);
      }
    }

    fetchTierLimits();
  }, []);

  const getTierLimit = (tierId: string) => {
    if (!tierLimits) return null;
    return tierLimits.tiers.find((tier) => tier.tier === tierId);
  };

  const formatLimitText = (limit: number) => {
    if (limit >= 1000) {
      return "Unlimited product searches";
    }
    return `${limit} product searches per month`;
  };

  return {
    tierLimits,
    loading,
    error,
    getTierLimit,
    formatLimitText,
  };
}
