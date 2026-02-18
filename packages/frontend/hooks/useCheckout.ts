// Custom hook for checkout flow
"use client";

import posthog from "posthog-js";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { type CheckoutRequest, subscriptionApi } from "@/lib/api/subscriptions";

// Custom hook for checkout flow

export function useCheckout() {
  const { getToken } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startCheckout = async (priceId: string) => {
    setIsLoading(true);
    setError(null);

    // Track checkout started event
    posthog.capture("checkout_started", {
      price_id: priceId,
      source: "pricing_page",
    });

    try {
      // Get Clerk token - try template first, then default
      let token = await getToken({ template: "default" });
      if (!token) {
        token = await getToken();
      }

      const request: CheckoutRequest = {
        price_id: priceId,
        success_url: `${window.location.origin}/checkout/success`,
        cancel_url: `${window.location.origin}/pricing`,
      };

      const response = await subscriptionApi.createCheckout(request, token);

      // Redirect to Paddle checkout
      window.location.href = response.checkout_url;
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to start checkout";
      setError(errorMessage);
      setIsLoading(false);

      // Track checkout error
      posthog.capture("checkout_error", {
        price_id: priceId,
        error: errorMessage,
      });
      posthog.captureException(err);
    }
  };

  return {
    startCheckout,
    isLoading,
    error,
  };
}
