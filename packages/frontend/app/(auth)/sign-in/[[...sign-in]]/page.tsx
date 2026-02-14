"use client";

import { useEffect } from "react";

import { SignIn } from "@clerk/nextjs";

import { useAnalytics } from "../../../../hooks/useAnalytics";

export default function SignInPage() {
  const { trackPageView, trackUserJourney } = useAnalytics();

  // Track sign-in page view
  useEffect(() => {
    trackPageView("sign_in_page");
  }, [trackPageView]);

  // Track sign-in events
  useEffect(() => {
    function handleSignIn() {
      trackUserJourney.signIn("clerk");
    }

    // Listen for sign-in success
    window.addEventListener("clerk-sign-in-complete", handleSignIn);

    return () => {
      window.removeEventListener("clerk-sign-in-complete", handleSignIn);
    };
  }, [trackUserJourney]);

  return (
    <div className="container max-w-md mx-auto px-4 py-20">
      <div className="flex flex-col items-center gap-8">
        <div className="flex flex-col gap-4 text-center">
          <h1 className="text-4xl font-bold">Welcome Back</h1>
          <p className="text-lg text-muted-foreground">
            Sign in to your Clausea account to continue
          </p>
        </div>
        <div className="w-full max-w-[400px]">
          <SignIn
            appearance={{
              elements: {
                rootBox: "w-full",
                card: "shadow-none border-0",
                headerTitle: "hidden",
                headerSubtitle: "hidden",
              },
            }}
            fallbackRedirectUrl="/products"
          />
        </div>
      </div>
    </div>
  );
}
