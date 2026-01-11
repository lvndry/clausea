"use client";

import { CheckCircle } from "lucide-react";
import Link from "next/link";
import posthog from "posthog-js";

import { useEffect, useRef, useState } from "react";

import type { SubscriptionResponse } from "@/lib/api/subscriptions";
import { subscriptionApi } from "@/lib/api/subscriptions";

export default function CheckoutSuccessPage() {
  const [subscription, setSubscription] = useState<SubscriptionResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const hasTrackedRef = useRef(false);

  useEffect(() => {
    // Fetch subscription after checkout
    subscriptionApi
      .getSubscription()
      .then((sub) => {
        setSubscription(sub);
        // Track checkout completed event only once when subscription is loaded
        if (sub && !hasTrackedRef.current) {
          hasTrackedRef.current = true;
          posthog.capture("checkout_completed", {
            tier: sub.tier,
            subscription_status: sub.status,
            current_period_end: sub.current_period_end,
          });
        }
      })
      .catch((err) => {
        console.error(err);
        posthog.captureException(err);
      })
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-white to-gray-50 px-4 dark:from-gray-950 dark:to-gray-900">
      <div className="max-w-md text-center">
        <div className="mb-6 flex justify-center">
          <CheckCircle className="h-20 w-20 text-green-500" />
        </div>

        <h1 className="mb-4 text-4xl font-bold text-gray-900 dark:text-white">
          Welcome to Clausea!
        </h1>

        <p className="mb-8 text-lg text-gray-600 dark:text-gray-400">
          {isLoading
            ? "Loading your subscription..."
            : subscription
              ? `Your ${subscription.tier} plan is now active. Start analyzing privacy policies with unlimited access!`
              : "Your subscription is being activated. This may take a few moments."}
        </p>

        <div className="space-y-4">
          <Link
            href="/products"
            className="block rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-8 py-3 font-semibold text-white transition-colors hover:from-purple-700 hover:to-pink-700"
          >
            Browse Products
          </Link>

          <Link
            href="/pricing"
            className="block text-gray-600 underline hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
          >
            View Pricing Plans
          </Link>
        </div>

        {subscription && subscription.current_period_end && (
          <p className="mt-8 text-sm text-gray-500 dark:text-gray-400">
            Your subscription renews on{" "}
            {new Date(subscription.current_period_end).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
  );
}
