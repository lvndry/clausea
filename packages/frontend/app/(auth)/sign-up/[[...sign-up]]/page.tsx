"use client";

import { useEffect } from "react";

import { SignUp } from "@clerk/nextjs";

import { useAnalytics } from "../../../../hooks/useAnalytics";

export default function SignUpPage() {
  const { trackPageView, trackUserJourney } = useAnalytics();

  // Track sign-up page view
  useEffect(() => {
    trackPageView("sign_up_page");
  }, [trackPageView]);

  // Track sign-up events
  useEffect(() => {
    function handleSignUp() {
      trackUserJourney.signUp("clerk");
    }

    // Listen for sign-up success
    window.addEventListener("clerk-sign-up-complete", handleSignUp);

    return () => {
      window.removeEventListener("clerk-sign-up-complete", handleSignUp);
    };
  }, [trackUserJourney]);

  return (
    <div className="container max-w-md mx-auto px-4 py-20">
      <div className="flex flex-col items-center gap-8">
        <div className="flex flex-col gap-4 text-center">
          <h1 className="text-4xl font-bold">Join Clausea</h1>
          <p className="text-lg text-muted-foreground">
            Create your account to start analyzing legal documents
          </p>
        </div>
        <div className="w-full max-w-[400px]">
          <SignUp
            appearance={{
              elements: {
                rootBox: "w-full",
                card: "shadow-none border-0",
                headerTitle: "hidden",
                headerSubtitle: "hidden",
              },
            }}
            signInUrl="/sign-in"
            fallbackRedirectUrl="/onboarding"
          />
        </div>
      </div>
    </div>
  );
}
