"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import posthog from "posthog-js";

import { type ReactNode, Suspense, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  CheckoutEventNames,
  type Paddle,
  initializePaddle,
} from "@paddle/paddle-js";

type CheckoutViewState = "loading" | "opening" | "closed" | "error";

function getPaddleEnvironment(): "production" | "sandbox" {
  return process.env.NEXT_PUBLIC_PADDLE_ENVIRONMENT === "production"
    ? "production"
    : "sandbox";
}

function getCheckoutTheme(): "light" | "dark" {
  if (
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark")
  ) {
    return "dark";
  }
  return "light";
}

function CheckoutPageContent() {
  const searchParams = useSearchParams();
  const transactionId = searchParams.get("_ptxn");

  if (!transactionId) {
    return (
      <CheckoutShell>
        <AlertCircle className="mb-6 h-16 w-16 text-muted-foreground" />
        <h1 className="mb-3 text-2xl font-bold text-foreground sm:text-3xl">
          No checkout session found
        </h1>
        <p className="mb-8 max-w-md text-muted-foreground">
          Choose a plan on pricing to start checkout.
        </p>
        <Button asChild size="lg">
          <Link href="/pricing">View pricing</Link>
        </Button>
      </CheckoutShell>
    );
  }

  return <CheckoutOverlay transactionId={transactionId} />;
}

function CheckoutOverlay({ transactionId }: { transactionId: string }) {
  const clientToken = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
  const [viewState, setViewState] = useState<CheckoutViewState>(
    clientToken ? "loading" : "error",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(
    clientToken
      ? null
      : "Checkout is temporarily unavailable. Please try again in a few minutes.",
  );
  const paddleRef = useRef<Paddle | null>(null);
  const openedRef = useRef(false);

  useEffect(() => {
    if (!clientToken) return;

    let cancelled = false;

    (async () => {
      try {
        const paddle = await initializePaddle({
          token: clientToken,
          environment: getPaddleEnvironment(),
          checkout: {
            settings: {
              displayMode: "overlay",
              theme: getCheckoutTheme(),
              locale: "en",
            },
          },
          eventCallback: (event) => {
            if (event.name === CheckoutEventNames.CHECKOUT_COMPLETED) {
              posthog.capture("checkout_overlay_completed", {
                transaction_id: transactionId,
              });
              window.location.assign("/checkout/success");
              return;
            }

            if (event.name === CheckoutEventNames.CHECKOUT_CLOSED) {
              setViewState("closed");
              return;
            }

            if (
              event.name === CheckoutEventNames.CHECKOUT_ERROR ||
              event.name === CheckoutEventNames.CHECKOUT_FAILED
            ) {
              setViewState("error");
              setErrorMessage(
                "We couldn't complete checkout. Please try again from pricing.",
              );
              posthog.capture("checkout_overlay_error", {
                transaction_id: transactionId,
                event: event.name,
              });
            }
          },
        });

        if (cancelled) return;

        if (!paddle) {
          setViewState("error");
          setErrorMessage(
            "We couldn't load checkout. Please try again from pricing.",
          );
          return;
        }

        paddleRef.current = paddle;
        setViewState("opening");

        if (!openedRef.current) {
          openedRef.current = true;
          paddle.Checkout.open({ transactionId });
        }
      } catch (err) {
        if (!cancelled) {
          setViewState("error");
          setErrorMessage(
            "Something went wrong opening checkout. Please try again.",
          );
          posthog.captureException(err);
        }
      }
    })();

    return () => {
      cancelled = true;
      openedRef.current = false;
      if (paddleRef.current) {
        paddleRef.current.Checkout.close();
      }
    };
  }, [clientToken, transactionId]);

  if (viewState === "closed") {
    return (
      <CheckoutShell>
        <h1 className="mb-3 text-2xl font-bold text-foreground sm:text-3xl">
          Checkout closed
        </h1>
        <p className="mb-8 max-w-md text-muted-foreground">
          You can return to pricing to continue with your subscription.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/pricing">Back to pricing</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/products">Browse products</Link>
          </Button>
        </div>
      </CheckoutShell>
    );
  }

  if (viewState === "error") {
    return (
      <CheckoutShell>
        <AlertCircle className="mb-6 h-16 w-16 text-destructive" />
        <h1 className="mb-3 text-2xl font-bold text-foreground sm:text-3xl">
          Unable to open checkout
        </h1>
        <p className="mb-8 max-w-md text-muted-foreground">
          {errorMessage ?? "Please try again from pricing."}
        </p>
        <Button asChild size="lg">
          <Link href="/pricing">View pricing</Link>
        </Button>
      </CheckoutShell>
    );
  }

  return (
    <CheckoutShell>
      <Loader2 className="mb-6 h-12 w-12 animate-spin text-primary" />
      <h1 className="mb-3 text-2xl font-bold text-foreground sm:text-3xl">
        {viewState === "opening" ? "Checkout is open" : "Preparing checkout"}
      </h1>
      <p className="max-w-md text-muted-foreground">
        {viewState === "opening"
          ? "Complete payment in the checkout window. This page will update when you're done."
          : "Loading secure checkout..."}
      </p>
    </CheckoutShell>
  );
}

function CheckoutShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 py-12 text-center">
      {children}
    </div>
  );
}

function CheckoutPageFallback() {
  return (
    <CheckoutShell>
      <Loader2 className="mb-6 h-12 w-12 animate-spin text-primary" />
      <h1 className="mb-3 text-2xl font-bold text-foreground sm:text-3xl">
        Preparing checkout
      </h1>
      <p className="max-w-md text-muted-foreground">
        Loading secure checkout...
      </p>
    </CheckoutShell>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense fallback={<CheckoutPageFallback />}>
      <CheckoutPageContent />
    </Suspense>
  );
}
