import { useEffect } from "react";

import { useUser } from "@clerk/nextjs";

import {
  identifyUser,
  trackPageView,
  trackUserJourney,
} from "../lib/analytics";

export function useAnalytics() {
  const { user, isLoaded } = useUser();

  useEffect(() => {
    if (isLoaded && user) {
      identifyUser(user);
    }
  }, [isLoaded, user]);

  return {
    trackPageView,
    trackUserJourney,
    user,
    isLoaded,
  };
}
