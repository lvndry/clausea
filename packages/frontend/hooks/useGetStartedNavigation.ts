"use client";

import { useRouter } from "next/navigation";

import { AUTH_ROUTES, getSignedInDestination } from "@/lib/auth-routes";
import { useAuth } from "@clerk/nextjs";

import { useUserData } from "./useUserData";

export function useGetStartedNavigation() {
  const router = useRouter();
  const { isSignedIn, isLoaded } = useAuth();
  const { userData, loading: userDataLoading } = useUserData();

  const isSignedInReady = isLoaded && isSignedIn && !userDataLoading;

  const destination =
    !isLoaded || !isSignedIn
      ? AUTH_ROUTES.signUp
      : userDataLoading
        ? AUTH_ROUTES.onboarding
        : getSignedInDestination(userData?.onboarding_completed);

  const navigate = () => {
    if (!isLoaded) {
      return;
    }

    if (!isSignedIn) {
      router.push(AUTH_ROUTES.signUp);
      return;
    }

    if (userDataLoading) {
      return;
    }

    router.push(getSignedInDestination(userData?.onboarding_completed));
  };

  return {
    destination,
    navigate,
    isNavigationReady: isLoaded && (!isSignedIn || !userDataLoading),
  };
}
