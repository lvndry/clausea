// Custom hook for billing portal access
"use client";

import posthog from "posthog-js";

import { useState } from "react";

import { subscriptionApi } from "@/lib/api/subscriptions";

// Custom hook for billing portal access

export function useBillingPortal() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openPortal = async () => {
    setIsLoading(true);
    setError(null);

    // Track billing portal opened event
    posthog.capture("billing_portal_opened", {
      source: "dashboard",
    });

    try {
      const response = await subscriptionApi.getBillingPortal();

      // Open portal in new tab
      window.open(response.portal_url, "_blank");
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to open billing portal";
      setError(errorMessage);

      // Track billing portal error
      posthog.capture("billing_portal_error", {
        error: errorMessage,
      });
      posthog.captureException(err);
    } finally {
      setIsLoading(false);
    }
  };

  return {
    openPortal,
    isLoading,
    error,
  };
}
