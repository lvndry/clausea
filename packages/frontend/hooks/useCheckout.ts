// Custom hook for checkout flow
"use client";

import posthog from "posthog-js";

import { useState } from "react";

import { type CheckoutRequest, subscriptionApi } from "@/lib/api/subscriptions";
import { useAuth } from "@clerk/nextjs";

function getSignInRedirectUrl(): string {
  if (typeof window === "undefined") {
    return "/sign-in?redirect_url=%2Fpricing";
  }

  return `/sign-in?redirect_url=${encodeURIComponent(
    `${window.location.pathname}${window.location.search}`,
  )}`;
}

export function useCheckout() {
  const { isSignedIn, isLoaded } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startCheckout = async (priceId: string) => {
    if (!isLoaded) {
      return;
    }

    if (!isSignedIn) {
      window.location.assign(getSignInRedirectUrl());
      return;
    }

    setIsLoading(true);
    setError(null);

    posthog.capture("checkout_started", {
      price_id: priceId,
      source: "pricing_page",
    });

    try {
      const request: CheckoutRequest = {
        price_id: priceId,
      };

      const response = await subscriptionApi.createCheckout(request);
      const checkoutUrl = response.checkout_url?.trim();

      if (!checkoutUrl) {
        throw new Error(
          "We couldn't start checkout. Please try again in a moment.",
        );
      }

      window.location.assign(checkoutUrl);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to start checkout";
      setError(errorMessage);
      setIsLoading(false);

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
