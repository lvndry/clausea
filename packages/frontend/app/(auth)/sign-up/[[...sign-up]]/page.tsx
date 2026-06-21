"use client";

import { useRouter } from "next/navigation";

import { useEffect } from "react";

import { getSignedInDestination } from "@/lib/auth-routes";
import { SignUp, useAuth } from "@clerk/nextjs";

import { useAnalytics } from "../../../../hooks/useAnalytics";
import { useUserData } from "../../../../hooks/useUserData";

export default function SignUpPage() {
  const router = useRouter();
  const { isSignedIn, isLoaded } = useAuth();
  const { userData, loading: userDataLoading } = useUserData();
  const { trackPageView, trackUserJourney } = useAnalytics();

  useEffect(() => {
    if (!isLoaded || !isSignedIn || userDataLoading) {
      return;
    }

    router.replace(getSignedInDestination(userData?.onboarding_completed));
  }, [isLoaded, isSignedIn, userDataLoading, userData, router]);

  // Track sign-up page view
  useEffect(() => {
    if (isSignedIn) {
      return;
    }

    trackPageView("sign_up_page");
  }, [trackPageView, isSignedIn]);

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

  if (!isLoaded || (isSignedIn && userDataLoading)) {
    return null;
  }

  if (isSignedIn) {
    return null;
  }

  return (
    <div className="max-w-md mx-auto px-4 py-20">
      <div className="flex flex-col items-center gap-8">
        <div className="flex flex-col gap-4 text-center">
          <h1 className="text-4xl font-bold">Join Clausea</h1>
          <p className="text-lg text-muted-foreground">
            Create your account to start analyzing legal agreements and policies
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
            forceRedirectUrl="/onboarding"
            fallbackRedirectUrl="/onboarding"
          />
        </div>
      </div>
    </div>
  );
}
